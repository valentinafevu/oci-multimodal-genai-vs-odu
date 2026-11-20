# IAM policies (OCI) para OCR app

Usa estas politicas en el **tenancy root** o en el compartimento padre segun tu gobierno.

## 1) Dynamic Group (Container Instance)

Regla recomendada para incluir la Container Instance:

```text
ALL {resource.type = 'computecontainerinstance', resource.compartment.id = '<APP_COMPARTMENT_OCID>'}
```

## 2) Policies minimas para la app

Reemplaza placeholders antes de ejecutar.

```text
Allow dynamic-group <DYNAMIC_GROUP_NAME> to read objectstorage-namespaces in tenancy
Allow dynamic-group <DYNAMIC_GROUP_NAME> to manage objects in compartment <APP_COMPARTMENT_NAME> where target.bucket.name = '<BUCKET_NAME>'
Allow dynamic-group <DYNAMIC_GROUP_NAME> to manage ai-document-family in compartment <APP_COMPARTMENT_NAME>
Allow dynamic-group <DYNAMIC_GROUP_NAME> to use virtual-network-family in compartment <NETWORK_COMPARTMENT_NAME>
```

Si guardas configuracion en Vault:

```text
Allow dynamic-group <DYNAMIC_GROUP_NAME> to read secret-family in compartment <SECURITY_COMPARTMENT_NAME>
Allow dynamic-group <DYNAMIC_GROUP_NAME> to read keys in compartment <SECURITY_COMPARTMENT_NAME>
```

## 3) Policy para pipeline de despliegue (usuario/grupo CI)

```text
Allow group <CI_GROUP_NAME> to manage repos in compartment <APP_COMPARTMENT_NAME>
Allow group <CI_GROUP_NAME> to manage cluster-family in compartment <APP_COMPARTMENT_NAME>
Allow group <CI_GROUP_NAME> to manage compute-container-family in compartment <APP_COMPARTMENT_NAME>
Allow group <CI_GROUP_NAME> to manage load-balancers in compartment <APP_COMPARTMENT_NAME>
Allow group <CI_GROUP_NAME> to use virtual-network-family in compartment <NETWORK_COMPARTMENT_NAME>
```

## 4) Validacion rapida

```bash
oci iam policy list --compartment-id <TENANCY_OCID> --all
oci iam dynamic-group list --all
```

## 5) Seguridad recomendada adicional

- Restringe `manage objects` al bucket objetivo (ya incluido arriba).
- Separa compartimento de red y de app.
- Activa rotacion de secretos en Vault.
- Habilita Cloud Guard + Logging de auditoria.
