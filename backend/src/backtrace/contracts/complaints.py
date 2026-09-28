import datetime as dt

from pydantic import BaseModel


class ComplaintOut(BaseModel):
    complaint_id: str
    customer_id: str
    received_at: dt.datetime
    channel: str
    text: str
    product: str
    region: str

    model_config = {"from_attributes": True}
