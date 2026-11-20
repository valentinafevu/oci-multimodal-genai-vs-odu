#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEPLOY_ENV_FILE="${DEPLOY_ENV_FILE:-${ROOT_DIR}/scripts/deploy.env}"

if [[ ! -f "${DEPLOY_ENV_FILE}" ]]; then
  echo "Missing deploy env file: ${DEPLOY_ENV_FILE}"
  echo "Copy scripts/deploy.env.template to scripts/deploy.env and fill values."
  exit 1
fi

# shellcheck disable=SC1090
source "${DEPLOY_ENV_FILE}"

required_vars=(
  OCI_REGION OCI_TENANCY_NAMESPACE OCI_TENANCY_NAME APP_NAME IMAGE_TAG
  OCI_AUTH_MODE NAMESPACE BUCKET_NAME COMPARTMENT_OCID OCR_OUTPUT_PREFIX MAX_UPLOAD_MB
  OCI_COMPARTMENT_OCID SUBNET_OCID_CONTAINER SUBNET_OCID_LB
  CONTAINER_INSTANCE_SHAPE CONTAINER_CPU CONTAINER_MEMORY_IN_GBS
  LB_SHAPE LB_MIN_BW LB_MAX_BW LISTENER_PORT BACKEND_PORT HEALTHCHECK_PORT
)

for var_name in "${required_vars[@]}"; do
  if [[ -z "${!var_name:-}" ]]; then
    echo "Variable ${var_name} is required in ${DEPLOY_ENV_FILE}"
    exit 1
  fi
done

IMAGE_URI="${OCI_REGION}.ocir.io/${OCI_TENANCY_NAMESPACE}/${APP_NAME}:${IMAGE_TAG}"

echo "[1/6] Logging into OCIR"
echo "Use your OCI auth token when prompted for password."
docker login "${OCI_REGION}.ocir.io" -u "${OCI_TENANCY_NAME}/${OCI_TENANCY_NAMESPACE}"

echo "[2/6] Building image: ${IMAGE_URI}"
docker build -t "${IMAGE_URI}" "${ROOT_DIR}"

echo "[3/6] Pushing image"
docker push "${IMAGE_URI}"

echo "[4/6] Creating Container Instance"
container_instance_json_file="$(mktemp)"
cat > "${container_instance_json_file}" <<JSON
{
  "displayName": "${APP_NAME}",
  "compartmentId": "${OCI_COMPARTMENT_OCID}",
  "shape": "${CONTAINER_INSTANCE_SHAPE}",
  "shapeConfig": {
    "ocpus": ${CONTAINER_CPU},
    "memoryInGBs": ${CONTAINER_MEMORY_IN_GBS}
  },
  "vnics": [
    {
      "subnetId": "${SUBNET_OCID_CONTAINER}",
      "isPublicIpAssigned": false,
      "displayName": "${APP_NAME}-vnic"
    }
  ],
  "containers": [
    {
      "displayName": "${APP_NAME}",
      "imageUrl": "${IMAGE_URI}",
      "isResourcePrincipalDisabled": false,
      "environmentVariables": {
        "OCI_AUTH_MODE": "${OCI_AUTH_MODE}",
        "NAMESPACE": "${NAMESPACE}",
        "BUCKET_NAME": "${BUCKET_NAME}",
        "COMPARTMENT_OCID": "${COMPARTMENT_OCID}",
        "OCR_OUTPUT_PREFIX": "${OCR_OUTPUT_PREFIX}",
        "MAX_UPLOAD_MB": "${MAX_UPLOAD_MB}",
        "OCI_REGION": "${OCI_REGION}"
      }
    }
  ]
}
JSON

container_instance_id="$(oci container-instances container-instance create \
  --from-json "file://${container_instance_json_file}" \
  --wait-for-state ACTIVE \
  --query 'data.id' --raw-output)"
rm -f "${container_instance_json_file}"

private_ip="$(oci container-instances container-instance get \
  --container-instance-id "${container_instance_id}" \
  --query 'data.vnics[0]."private-ip"' \
  --raw-output)"

echo "Container Instance ID: ${container_instance_id}"
echo "Container private IP: ${private_ip}"

echo "[5/6] Creating Load Balancer"
lb_id="$(oci lb load-balancer create \
  --compartment-id "${OCI_COMPARTMENT_OCID}" \
  --display-name "${APP_NAME}-lb" \
  --shape-name "${LB_SHAPE}" \
  --shape-details "{\"minimumBandwidthInMbps\":${LB_MIN_BW},\"maximumBandwidthInMbps\":${LB_MAX_BW}}" \
  --subnet-ids "[\"${SUBNET_OCID_LB}\"]" \
  --wait-for-state ACTIVE \
  --query 'data.id' --raw-output)"

echo "Load Balancer ID: ${lb_id}"

echo "[6/6] Configuring backend set and listener"
oci lb backend-set create \
  --load-balancer-id "${lb_id}" \
  --name "${APP_NAME}-bs" \
  --policy ROUND_ROBIN \
  --health-checker "{\"protocol\":\"HTTP\",\"port\":${HEALTHCHECK_PORT},\"urlPath\":\"/_stcore/health\",\"intervalInMillis\":10000,\"timeoutInMillis\":3000,\"retries\":3,\"returnCode\":200}" \
  --wait-for-state SUCCEEDED >/dev/null

oci lb backend create \
  --load-balancer-id "${lb_id}" \
  --backend-set-name "${APP_NAME}-bs" \
  --ip-address "${private_ip}" \
  --port "${BACKEND_PORT}" \
  --weight 1 \
  --wait-for-state SUCCEEDED >/dev/null

if [[ -n "${CERTIFICATE_NAME:-}" ]]; then
  oci lb listener create \
    --load-balancer-id "${lb_id}" \
    --name "${APP_NAME}-listener" \
    --default-backend-set-name "${APP_NAME}-bs" \
    --port "${LISTENER_PORT}" \
    --protocol HTTP \
    --ssl-configuration "{\"certificateName\":\"${CERTIFICATE_NAME}\",\"verifyPeerCertificate\":false}" \
    --wait-for-state SUCCEEDED >/dev/null
  protocol="https"
else
  if [[ "${LISTENER_PORT}" == "443" ]]; then
    echo "CERTIFICATE_NAME is empty and LISTENER_PORT=443. Falling back to port 80."
    LISTENER_PORT=80
  fi
  oci lb listener create \
    --load-balancer-id "${lb_id}" \
    --name "${APP_NAME}-listener" \
    --default-backend-set-name "${APP_NAME}-bs" \
    --port "${LISTENER_PORT}" \
    --protocol HTTP \
    --wait-for-state SUCCEEDED >/dev/null
  protocol="http"
fi

public_ip="$(oci lb load-balancer get --load-balancer-id "${lb_id}" --query 'data."ip-addresses"[0]."ip-address"' --raw-output)"

echo "Deployment complete"
echo "Image URI: ${IMAGE_URI}"
echo "Load Balancer URL: ${protocol}://${public_ip}"
if [[ -n "${CERTIFICATE_NAME:-}" ]]; then
  echo "TLS configured with certificate: ${CERTIFICATE_NAME}"
fi
