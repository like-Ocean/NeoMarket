from pydantic import BaseModel

class ReserveItem(BaseModel):
    sku_id: str
    quantity: int