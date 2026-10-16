from sqlalchemy import ForeignKey
import uuid
from datetime import datetime
import sqlalchemy
from typing import Optional
from Database.base import Base
from sqlalchemy import String, text, Numeric, JSON,Boolean, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Scrapper_Record_Map(Base):
    #this class creates and manages a table in db named Scrapper_record_maps
    #it's purpose is to store maps of data coming from scrapper into the standard_record format
    # first time created through AI which is them stored in db for reuse
    __tablename__="scrapper_record_maps"
    id: Mapped[str] =mapped_column(String(100),primary_key=True,default=lambda: str(uuid.uuid4()))
    scrapper_id:Mapped[str]=mapped_column(String(100),ForeignKey("sources.id",ondelete="CASCADE"),unique=True,index=True)
    scrapper_map:Mapped[dict]=mapped_column(JSON(),nullable=False)
    scrapper_hash:Mapped[Optional[str]]=mapped_column(String(64))
    reviewed:Mapped[bool]=mapped_column(Boolean,nullable=False,default=False,server_default="false")
    created_at:Mapped[datetime]=mapped_column(nullable=False,server_default=func.now())
    updated_at:Mapped[datetime| None]=mapped_column(onupdate=func.now())


