import base64
import os
from pathlib import Path

import streamlit as st

from ocr_service import OcrService


st.set_page_config(page_title="OCR Document Viewer", layout="wide")
st.title("Carga un documento y visualiza el texto extraido")
st.caption("Sube un PDF o imagen, y veras el contenido detectado por OCR a la derecha.")

max_upload_mb = int(os.getenv("MAX_UPLOAD_MB", "10"))

uploaded_file = st.file_uploader(
    "Selecciona un documento",
    type=["pdf", "png", "jpg", "jpeg", "tiff", "bmp"],
    help=f"Tamano maximo recomendado: {max_upload_mb} MB",
)

if uploaded_file:
    col_left, col_right = st.columns(2)
    file_bytes = uploaded_file.getvalue()
    file_name = Path(uploaded_file.name).name
    file_size_mb = len(file_bytes) / (1024 * 1024)

    if file_size_mb > max_upload_mb:
        st.error(
            f"El archivo pesa {file_size_mb:.2f} MB y supera el limite de {max_upload_mb} MB."
        )
        st.stop()

    with col_left:
        st.subheader("Documento")
        mime_type = uploaded_file.type or "application/octet-stream"

        if mime_type == "application/pdf" or file_name.lower().endswith(".pdf"):
            b64_pdf = base64.b64encode(file_bytes).decode("utf-8")
            pdf_view = (
                f'<iframe src="data:application/pdf;base64,{b64_pdf}" '
                'width="100%" height="650" type="application/pdf"></iframe>'
            )
            st.markdown(pdf_view, unsafe_allow_html=True)
        else:
            st.image(file_bytes, caption=file_name, use_container_width=True)

    with col_right:
        st.subheader("Texto extraido")
        if st.button("Extraer texto", type="primary"):
            try:
                with st.spinner("Procesando OCR en OCI..."):
                    service = OcrService()
                    extracted_text = service.run_ocr(
                        file_bytes=file_bytes,
                        original_name=file_name,
                    )

                st.text_area(
                    "Resultado OCR",
                    value=extracted_text or "No se encontro texto.",
                    height=650,
                )
            except Exception as exc:  # noqa: BLE001
                st.error(f"Error al extraer el texto: {exc}")
else:
    st.info("Primero carga un documento para habilitar la extraccion.")
