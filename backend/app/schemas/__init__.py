from app.schemas.ai import AdviceRequest, ChatRequest
from app.schemas.inventory import InventoryOpCreate, InventoryLogOut, InventorySummary
from app.schemas.product import (
    ProductCreate,
    ProductOut,
    ProductUpdate,
    SkuMappingCreate,
    SkuMappingOut,
)
from app.schemas.shop import ShopCreate, ShopOut, ShopUpdate
from app.schemas.user import (
    ChangePasswordRequest,
    LoginRequest,
    ProfileOut,
    ProfileUpdate,
    ResetPasswordRequest,
    UserCreate,
    UserOut,
)

__all__ = [
    "AdviceRequest",
    "ChatRequest",
    "InventoryOpCreate",
    "InventoryLogOut",
    "InventorySummary",
    "ProductCreate",
    "ProductOut",
    "ProductUpdate",
    "SkuMappingCreate",
    "SkuMappingOut",
    "ShopCreate",
    "ShopOut",
    "ShopUpdate",
    "ChangePasswordRequest",
    "LoginRequest",
    "ProfileOut",
    "ProfileUpdate",
    "ResetPasswordRequest",
    "UserCreate",
    "UserOut",
]
