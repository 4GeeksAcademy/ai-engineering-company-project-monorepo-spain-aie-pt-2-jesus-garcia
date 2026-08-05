from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query

from database import get_db
from models import Supplier, SupplierCreate, SupplierUpdate

router = APIRouter(prefix="/suppliers", tags=["suppliers"])


@router.get(
    "",
    response_model=list[Supplier],
    summary="Listar proveedores con filtros opcionales",
)
def list_suppliers(
    country: str | None = Query(None, description="Filtrar por país: USA o Spain"),
    category: str | None = Query(None, description="Filtrar por categoría"),
    status: str | None = Query(None, description="Filtrar por estado: active o suspended"),
) -> list[Supplier]:
    db = get_db()
    table = db.table("suppliers")

    results = []
    for doc in table.all():
        if country and doc.get("country") != country:
            continue
        if category and category not in doc.get("categories", []):
            continue
        if status and doc.get("status") != status:
            continue

        results.append(Supplier(id=str(doc.doc_id), **doc))

    db.close()
    return results


@router.get(
    "/{supplier_id}",
    response_model=Supplier,
    summary="Obtener un proveedor por ID",
)
def get_supplier(supplier_id: str) -> Supplier:
    db = get_db()
    table = db.table("suppliers")

    target_id = int(supplier_id) if supplier_id.isdigit() else supplier_id
    for doc in table.all():
        if doc.doc_id == target_id:
            db.close()
            return Supplier(id=str(doc.doc_id), **doc)

    db.close()
    raise HTTPException(status_code=404, detail=f"Supplier {supplier_id} not found")


@router.post(
    "",
    response_model=Supplier,
    status_code=201,
    summary="Crear un nuevo proveedor",
)
def create_supplier(payload: SupplierCreate) -> Supplier:
    db = get_db()
    table = db.table("suppliers")

    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "name": payload.name,
        "country": payload.country,
        "categories": payload.categories,
        "rate_per_shipment": payload.rate_per_shipment,
        "currency": payload.currency,
        "updated_at": now,
        "status": payload.status,
        "service_zone": payload.service_zone,
        "contact_email": payload.contact_email,
        "notes": payload.notes,
    }

    doc_id = table.insert(doc)
    db.close()

    return Supplier(id=str(doc_id), **doc)


@router.put(
    "/{supplier_id}",
    response_model=Supplier,
    summary="Actualizar un proveedor existente",
)
def update_supplier(supplier_id: str, payload: SupplierUpdate) -> Supplier:
    db = get_db()
    table = db.table("suppliers")

    target_id = int(supplier_id) if supplier_id.isdigit() else supplier_id
    doc = None
    for d in table.all():
        if d.doc_id == target_id:
            doc = d
            break

    if doc is None:
        db.close()
        raise HTTPException(status_code=404, detail=f"Supplier {supplier_id} not found")

    update_data = payload.model_dump(exclude_unset=True)

    if "rate_per_shipment" in update_data:
        update_data["updated_at"] = datetime.now(timezone.utc).isoformat()

    table.update(update_data, doc_ids=[target_id])

    for d in table.all():
        if d.doc_id == target_id:
            db.close()
            return Supplier(id=str(target_id), **d)

    db.close()
    raise HTTPException(status_code=404, detail=f"Supplier {supplier_id} not found")


@router.delete(
    "/{supplier_id}",
    status_code=204,
    summary="Eliminar un proveedor",
)
def delete_supplier(supplier_id: str) -> None:
    db = get_db()
    table = db.table("suppliers")

    target_id = int(supplier_id) if supplier_id.isdigit() else supplier_id
    found = False
    for d in table.all():
        if d.doc_id == target_id:
            found = True
            break

    if not found:
        db.close()
        raise HTTPException(status_code=404, detail=f"Supplier {supplier_id} not found")

    table.remove(doc_ids=[target_id])
    db.close()
