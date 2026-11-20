from pydantic import BaseModel, Field

class SourceCheck(BaseModel):
    source_id: str = Field(min_length=1,max_length=512)
    source_revision: str = Field(min_length=1,max_length=512)

class FileAcknowledgement(BaseModel):
    file_name: str
    drive_file_id: str = Field(min_length=1,max_length=512)

class TelegramReceipt(BaseModel):
    telegram_message_id: str = Field(min_length=1,max_length=128)
