from Database.models.scrapper_record_map import Scrapper_Record_Map
from Database.repositories.base import  BaseRepository
from Database.controller import session_scope
from Database.models.source import Source
from typing import Any, Optional, Dict
from sqlalchemy import select,update,delete,insert, func, or_
from sqlalchemy.orm import Session
import sys
from pathlib import Path

# root_dir=Path(__file__).resolve().parent.parent
# sys.path.append(str(root_dir))
# from Backend.scrappers.normalize import Normalize


class Scrapper_Record_Map_Repository(BaseRepository[Scrapper_Record_Map]):
    model=Scrapper_Record_Map

    @staticmethod
    def save_map(map_dict,code):
        if code == None:
            raise ValueError("No Source code provided by the scrapper")
        clean_code=str(code).strip().lower()
        with session_scope() as S:
            db_query=select(Source.id).where(func.lower(Source.code)==clean_code)
            scrapper_id=S.scalar(db_query)
            if not scrapper_id:
                raise ValueError(f"unable to get scrapper id of scrapper {code}")
            repo=Scrapper_Record_Map_Repository(S)
            record,created=repo.upsert_by(lookup_field="scrapper_id",
            lookup_value=scrapper_id,
            data={
                "scrapper_code":clean_code,
                "scrapper_map":map_dict,
            })
            status="Inserted New" if created else "Updated existing"
            print(f"Successfully {status.lower()} record map for scraper '{clean_code}' (ID: {record.id})")
        return record

    @staticmethod
    def get_map(map_dict=None,code=None):
        if map_dict!=None:
            Scrapper_Record_Map_Repository.save_map(map_dict,code)
        else:
            raise ValueError("Map dictionary is empty")
    @staticmethod
    def check_if_map_exists(scrapper_code) -> bool:
        if scrapper_code is None:
            raise ValueError("No scrapper_code recieved")
        with session_scope() as S:
            db_query=select(Scrapper_Record_Map.id).join(Source,
            Scrapper_Record_Map.scrapper_id==Source.id).where(func.lower(Source.code)==scrapper_code).limit(1)
            if S.scalar(db_query) is None:
                return False
        return True
    @staticmethod
    def get_scrapper_map_from_db(scrapper_code):
        if scrapper_code is None:
            raise ValueError("No scrapper_code received")
        clean_code = str(scrapper_code).strip().lower()

        with session_scope() as S:
            db_query = (
                select(Scrapper_Record_Map.scrapper_map).where(func.lower(Scrapper_Record_Map.scrapper_code) == clean_code)
            )
            result = S.scalar(db_query)
            if result is None:
                return {}
            return dict(result)

        
