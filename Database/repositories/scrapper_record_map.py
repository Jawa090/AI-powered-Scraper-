from Database.models.scrapper_record_map import Scrapper_Record_Map
from Database.repositories.base import  BaseRepository
from typing import Any, Optional
import sqlalchemy
from sqlalchemy import select,update,delete,insert
from sqlalchemy.orm import Session
import sys
from pathlib import Path

# root_dir=Path(__file__).resolve().parent.parent
# sys.path.append(str(root_dir))
# from Backend.scrappers.normalize import Normalize


class Scrapper_Record_Map_Repository(BaseRepository[Scrapper_Record_Map]):
    model=Scrapper_Record_Map

    @staticmethod
    def save_map(map_dict=None):
        ''
        pass

    @staticmethod
    def get_map(map_dict=None):
        pass
