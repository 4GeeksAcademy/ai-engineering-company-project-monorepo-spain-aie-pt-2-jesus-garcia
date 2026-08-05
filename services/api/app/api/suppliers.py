from fastapi import APIRouter, HTTPException, Query

from database import get_db
from models import Supplier

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
