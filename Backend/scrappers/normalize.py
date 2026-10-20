from sqlalchemy import true
from pathlib import Path
import sys
root_dir=Path(__file__).resolve().parent.parent.parent
sys.path.append(str(root_dir))
from Database.repositories.scrapper_record_map import Scrapper_Record_Map_Repository
from Backend.scrappers.base import StandardRecord
from dotenv import load_dotenv
import os
import json
from openai import OpenAI
import pandas as pd
from typing import Optional, Any


load_dotenv()

class Normalize():
    _instance = None

    def __new__(class_, *arguments, **keyarguments):
        # ensures only 1 instance of the class
        if class_._instance is None:
            class_._instance = super().__new__(class_)
        return class_._instance

    def __init__(self):
        # Initialize only once
        if not hasattr(self, "_initialized"):
            self.client = OpenAI(
                api_key=os.getenv("LLM_API_KEY"),
                base_url=os.getenv("LLM_BASE_URL")
            )
            self._initialized = True
    def map_exists(self,scrapper_code):
        if Scrapper_Record_Map_Repository.check_if_map_exists(scrapper_code):
            return True
        else:
            return False
    def create_map(self, raw_datapoint):
        # this creates the map and passes it to the DB for storage, also views it 
        """The raw data needs to contain a record type column
        and source code"""
        print("Raw data\n")
        print(raw_datapoint)
        standard_schema = StandardRecord.model_json_schema()["properties"]
        print("Standard Schema\n")
        print(standard_schema)
        response = self.client.chat.completions.create(
            model=os.getenv("LLM_MODEL"),
            response_format={"type": "json_object"},
            temperature=0.0,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a data mapping assistant. Compare the StandardRecord fields "
                        "with the user's raw_datapoint dictionary. Return a JSON object where "
                        "each key is a StandardRecord field name, and each value is the matching "
                        "key name from raw_datapoint (or null if no match exists)."
                    )
                },
                {
                    "role": "user",
                    "content": (
                        f"StandardRecord schema:\n{json.dumps(standard_schema)}\n\n"
                        f"Raw_datapoint\n{json.dumps(raw_datapoint, default=str)}"
                    )
                }
            ]
        )
        map_dict = json.loads(response.choices[0].message.content)
        print("Map\n")
        print(map_dict)
        code=raw_datapoint.get("source_code")
        print(code)
        Scrapper_Record_Map_Repository.get_map(map_dict,code)
        return map_dict

    def get_map_from_db(self,scrapper_code):
        map= Scrapper_Record_Map_Repository. get_scrapper_map_from_db(scrapper_code)
        if map is None:
            raise ValueError("No Map returned by DB")
        return map
    def normalize_data(
        self, field_map: Optional[dict[str, str]], raw: Optional[dict[str, Any]]
    ) -> Optional[StandardRecord]:
        """
        Normalize a raw scraped datapoint into a canonical StandardRecord
        using the LLM/DB-generated mapping.
        """
        if not raw or not isinstance(raw, dict):
            return None

        # Determine StandardRecord valid field names (Pydantic v1 & v2 compatible)
        std_fields = (
            set(StandardRecord.model_fields.keys())
            if hasattr(StandardRecord, "model_fields")
            else set(StandardRecord.__fields__.keys())
        )

        data: dict[str, Any] = {}
        mapped_raw_keys: set[str] = set()

        # 1. Map canonical fields according to field_map
        if isinstance(field_map, dict):
            for std_key, raw_key in field_map.items():
                if (
                    std_key in std_fields
                    and std_key != "extra"
                    and isinstance(raw_key, str)
                    and raw_key in raw
                ):
                    if raw[raw_key] is not None:
                        data[std_key] = raw[raw_key]
                    mapped_raw_keys.add(raw_key)

        # 2. Required field fallbacks if not mapped (track used fallback keys)
        if not data.get("source_code"):
            for candidate in ("source_code", "scrapper_code", "scraper_code"):
                if raw.get(candidate):
                    data["source_code"] = raw[candidate]
                    mapped_raw_keys.add(candidate)
                    break
            else:
                data["source_code"] = "unknown"
        data["source_code"] = str(data["source_code"]).strip().lower()

        if not data.get("record_kind"):
            for candidate in ("record_kind", "record_type"):
                if raw.get(candidate):
                    data["record_kind"] = raw[candidate]
                    mapped_raw_keys.add(candidate)
                    break
            else:
                data["record_kind"] = "company"

        # 3. Direct fallbacks for any standard field present in raw but unmapped/None
        for std_key in std_fields:
            if data.get(std_key) is None and std_key in raw and std_key != "extra":
                data[std_key] = raw[std_key]
                mapped_raw_keys.add(std_key)

        # 4. Pack all remaining unmapped raw fields into `extra`
        extra = dict(raw["extra"]) if isinstance(raw.get("extra"), dict) else {}
        for raw_k, raw_v in raw.items():
            if raw_k not in mapped_raw_keys and raw_k != "extra":
                extra[raw_k] = raw_v

        # Clean empty string due_at to avoid datetime validation error
        if data.get("due_at") == "":
            data["due_at"] = None

        data["extra"] = extra
        print("StandardRecord\n")
        print(StandardRecord(**data))

        return StandardRecord(**data)

normalizer = Normalize()

if __name__ == "__main__":
    raw_data={}
    excel_path=r"C:\Users\adil.zia\Desktop\Tasks\Task3\Google-Map-Scraping-Agent-for-Construction-Based-Projects-in-USA\ServicesFromGM.xlsx"
    df=pd.read_excel(excel_path)
    raw_data=df.iloc[165].to_dict()
    normalizer.create_map(raw_data)  
