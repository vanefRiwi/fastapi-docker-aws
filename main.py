import uuid
from pathlib import Path

from botocore.exceptions import BotoCoreError, ClientError
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlmodel import select
from src.models.image_model import Image
from src.models.product_model import Product, ProductCategories
from src.shared.database.session_db import SessionDep, get_session
from src.shared.storage.s3_client import S3_BUCKET_NAME, s3_client

app = FastAPI()

# Tipos de imagen permitidos: content-type -> extensiones válidas
ALLOWED_IMAGE_TYPES = {
    "image/jpeg": {".jpg", ".jpeg"},
    "image/png": {".png"},
    "image/webp": {".webp"},
    "image/gif": {".gif"},
}
MAX_IMAGE_SIZE = 5 * 1024 * 1024  # 5 MB


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/images", status_code=201)
def upload_image(session: SessionDep, file: UploadFile = File(...)):
    if not S3_BUCKET_NAME:
        raise HTTPException(status_code=500, detail="S3_BUCKET_NAME no está configurado")

    # 1. Validar tipo y extensión
    extension = Path(file.filename or "").suffix.lower()
    allowed_extensions = ALLOWED_IMAGE_TYPES.get(file.content_type)
    if allowed_extensions is None or extension not in allowed_extensions:
        raise HTTPException(
            status_code=415,
            detail="Formato no permitido. Usa JPG, PNG, WEBP o GIF",
        )

    # 2. Validar tamaño
    contents = file.file.read()
    if len(contents) == 0:
        raise HTTPException(status_code=422, detail="El archivo está vacío")
    if len(contents) > MAX_IMAGE_SIZE:
        raise HTTPException(status_code=413, detail="La imagen supera los 5 MB")

    # 3. Subir a S3 con Boto3 (nombre único para no sobrescribir)
    s3_key = f"images/{uuid.uuid4()}{extension}"
    try:
        s3_client.put_object(
            Bucket=S3_BUCKET_NAME,
            Key=s3_key,
            Body=contents,
            ContentType=file.content_type,
        )
    except (BotoCoreError, ClientError) as error:
        raise HTTPException(status_code=502, detail=f"No se pudo subir a S3: {error}")

    # 4. Guardar la referencia en PostgreSQL
    image = Image(
        original_filename=file.filename,
        s3_bucket=S3_BUCKET_NAME,
        s3_key=s3_key,
        content_type=file.content_type,
        size_bytes=len(contents),
    )
    session.add(image)
    session.commit()
    session.refresh(image)

    return {"message": "Imagen subida correctamente", "image": image}


@app.get("/images")
def list_images(session: SessionDep):
    images = session.exec(select(Image)).all()
    result = []
    for image in images:
        # URL temporal (10 min) para ver la imagen sin hacer público el bucket
        url = s3_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": image.s3_bucket, "Key": image.s3_key},
            ExpiresIn=600,
        )
        result.append({**image.model_dump(), "url": url})
    return result


class CreateProduct(BaseModel):
    name: str
    price: float
    quantity: int
    category: ProductCategories


@app.post("/product", status_code=201)
def create_product(product: CreateProduct, session: SessionDep):
    # 1. Buscar si el producto existe
    product_inDb = session.exec(
        select(Product).where(Product.name == product.name.lower().strip())
    ).one_or_none()

    # 2.1 Si existe enviar mensaje de error
    if product_inDb == None:

        if product.price <= 0:
            raise HTTPException(
                status_code=422,
                detail="El precio del producto debe ser superior a 0",
            )

        if product.quantity <= 0:
            raise HTTPException(
                status_code=422,
                detail="La cantidad del producto debe ser superior a 0",
            )

        product = Product(
            name=product.name,
            category=product.category,
            price=product.price,
            quantity=product.quantity,
        )
        session.add(product)
        session.commit()
        session.refresh(product)

        return product
    # 2.2 Si no existe continuar con la creacion
    else:
        raise HTTPException(
            status_code=409, detail="El producto ya existe en la base de datos"
        )


@app.get("/product")
def get_products(session: SessionDep):
    products = session.exec(select(Product)).all()

    return products


@app.delete("/product/{id}")
def delete_product(product_id: int, session: SessionDep):
    product = session.exec(select(Product).where(Product.id == product_id)).one()
    session.delete(product)
    session.commit()
