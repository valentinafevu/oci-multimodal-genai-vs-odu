import json
import logging
import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import oci
from dotenv import load_dotenv


@dataclass
class OcrConfig:
    namespace: str
    bucket_name: str
    compartment_ocid: str
    output_prefix: str = "ocr"


class OcrService:
    def __init__(self, profile: str = "DEFAULT") -> None:
        load_dotenv()

        signer, config = self._build_oci_auth(profile=profile)
        object_storage_client = oci.object_storage.ObjectStorageClient(config=config, signer=signer)
        ai_document_client = oci.ai_document.AIServiceDocumentClient(config=config, signer=signer)

        self.object_storage_client = object_storage_client
        self.ai_document_client = oci.ai_document.AIServiceDocumentClientCompositeOperations(
            ai_document_client
        )

        namespace = os.getenv("NAMESPACE")
        bucket_name = os.getenv("BUCKET_NAME")
        compartment_ocid = os.getenv("COMPARTMENT_OCID")

        missing = [
            name
            for name, value in {
                "NAMESPACE": namespace,
                "BUCKET_NAME": bucket_name,
                "COMPARTMENT_OCID": compartment_ocid,
            }.items()
            if not value
        ]

        if missing:
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")

        self.ocr_config = OcrConfig(
            namespace=namespace,
            bucket_name=bucket_name,
            compartment_ocid=compartment_ocid,
            output_prefix=os.getenv("OCR_OUTPUT_PREFIX", "ocr"),
        )

    @staticmethod
    def _build_oci_auth(profile: str):
        auth_mode = os.getenv("OCI_AUTH_MODE", "config_file").strip().lower()
        region = os.getenv("OCI_REGION", "").strip()
        config = {"region": region} if region else {}

        if auth_mode == "resource_principal":
            signer = oci.auth.signers.get_resource_principals_signer()
            return signer, config
        if auth_mode == "instance_principal":
            signer = oci.auth.signers.InstancePrincipalsSecurityTokenSigner()
            return signer, config
        if auth_mode == "config_file":
            cfg = oci.config.from_file(profile_name=profile)
            return None, cfg

        raise ValueError(
            "Invalid OCI_AUTH_MODE. Use one of: config_file, resource_principal, instance_principal."
        )

    def _upload_document(self, file_bytes: bytes, original_name: str) -> str:
        safe_name = Path(original_name).name
        object_name = f"{uuid.uuid4().hex}_{safe_name}"

        self.object_storage_client.put_object(
            namespace_name=self.ocr_config.namespace,
            bucket_name=self.ocr_config.bucket_name,
            object_name=object_name,
            put_object_body=file_bytes,
        )
        return object_name

    def _create_ocr_job(self, object_name: str):
        text_extraction_feature = oci.ai_document.models.DocumentTextExtractionFeature()

        input_location = oci.ai_document.models.ObjectStorageLocations(
            object_locations=[
                oci.ai_document.models.ObjectLocation(
                    namespace_name=self.ocr_config.namespace,
                    bucket_name=self.ocr_config.bucket_name,
                    object_name=object_name,
                )
            ]
        )

        output_location = oci.ai_document.models.OutputLocation(
            namespace_name=self.ocr_config.namespace,
            bucket_name=self.ocr_config.bucket_name,
            prefix=self.ocr_config.output_prefix,
        )

        create_details = oci.ai_document.models.CreateProcessorJobDetails(
            display_name="ocr-doc-job",
            compartment_id=self.ocr_config.compartment_ocid,
            input_location=input_location,
            output_location=output_location,
            processor_config=oci.ai_document.models.GeneralProcessorConfig(
                features=[text_extraction_feature]
            ),
        )

        response = self.ai_document_client.create_processor_job_and_wait_for_state(
            create_processor_job_details=create_details,
            wait_for_states=[oci.ai_document.models.ProcessorJob.LIFECYCLE_STATE_SUCCEEDED],
            waiter_kwargs={"max_wait_seconds": 600, "max_interval_seconds": 10},
        )
        return response

    def _read_ocr_result_json(self, job_id: str, object_name: str) -> dict:
        result_path = (
            f"{self.ocr_config.output_prefix}/{job_id}/"
            f"{self.ocr_config.namespace}_{self.ocr_config.bucket_name}/"
            f"results/{object_name}.json"
        )

        last_error: Optional[Exception] = None
        for _ in range(6):
            try:
                response = self.object_storage_client.get_object(
                    namespace_name=self.ocr_config.namespace,
                    bucket_name=self.ocr_config.bucket_name,
                    object_name=result_path,
                )
                raw = response.data.content.decode("utf-8")
                return json.loads(raw)
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                time.sleep(2)

        raise RuntimeError(
            f"Could not fetch OCR result at path '{result_path}'."
        ) from last_error

    @staticmethod
    def _extract_text(result_json: dict) -> str:
        text_lines = []
        pages = result_json.get("pages", [])
        for page in pages:
            for line in page.get("lines", []):
                line_text = line.get("text", "")
                if line_text:
                    text_lines.append(line_text)

        if text_lines:
            return "\n".join(text_lines)

        words = []
        for page in pages:
            for word in page.get("words", []):
                token = word.get("text", "")
                if token:
                    words.append(token)

        return " ".join(words).strip()

    def run_ocr(self, file_bytes: bytes, original_name: str) -> str:
        logging.info("Uploading file to OCI Object Storage")
        object_name = self._upload_document(file_bytes=file_bytes, original_name=original_name)

        logging.info("Creating OCI AI Document OCR job")
        ocr_response = self._create_ocr_job(object_name=object_name)
        job_id = ocr_response.data.id

        logging.info("Reading OCR result JSON from Object Storage")
        result_json = self._read_ocr_result_json(job_id=job_id, object_name=object_name)

        return self._extract_text(result_json)
