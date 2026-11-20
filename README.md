# OCR app (OCI AI Document)

App web en Streamlit para cargar un documento y ver el texto extraido en panel lateral.

## Requisitos locales

- Python 3.10+
- Credenciales OCI configuradas en `~/.oci/config` (perfil `DEFAULT`) para desarrollo local.
- Variables en `.env` (usa `.env.template` como base):
  - `NAMESPACE`
  - `BUCKET_NAME`
  - `COMPARTMENT_OCID`
  - `OCI_AUTH_MODE`

## Instalacion local

```bash
pip install -r requirements.txt
```

## Ejecutar local

```bash
streamlit run app.py
```

## Produccion en URL publica (OCI)

### Archivos preparados

- `Dockerfile`: imagen de produccion.
- `.streamlit/config.toml`: configuracion headless y limites.
- `scripts/deploy.env.template`: variables para despliegue.
- `scripts/deploy_oci.sh`: build + push + deploy en OCI Container Instances + Load Balancer.
- `docs/iam_policies.md`: politicas IAM de referencia.

### Pasos

1. Copia y completa variables de despliegue:

```bash
cp scripts/deploy.env.template scripts/deploy.env
```

2. Valida IAM / Dynamic Group usando `docs/iam_policies.md`.

3. Ejecuta el despliegue:

```bash
bash scripts/deploy_oci.sh
```

4. Al final el script imprime la URL publica del Load Balancer.

### Notas de seguridad

- En produccion usa `OCI_AUTH_MODE=resource_principal`.
- No guardes secretos en `.env` dentro del contenedor.
- Configura certificado TLS en Load Balancer (`CERTIFICATE_NAME`) para HTTPS.
- Define reglas de borrado en Object Storage para limpiar documentos y resultados OCR.

## Archivos principales de app

- `app.py`: interfaz web de carga y vista lado a lado.
- `ocr_service.py`: integracion con Object Storage + OCI AI Document OCR.
