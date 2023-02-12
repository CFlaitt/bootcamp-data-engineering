import datetime
from abc import ABC, abstractmethod
from typing import List
import json
import os
from schedule import repeat, every, run_pending
import time

import requests
import logging

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

class mercadobitcoinApi():

    def __init__(self, coin: str) -> None:
        self.coin = coin
        self.base_endpoint = "https://www.mercadobitcoin.net/api"

    @abstractmethod
    def _get_endpoint(self, **kwargs) -> str:
        pass

    def get_data(self, **kwargs) -> dict:
        endpoint = self._get_endpoint(**kwargs)
        logger.info(f"Getting data from endpoint: {endpoint}")
        response = requests.get(endpoint)
        response.raise_for_status()
        return response.json()

class daySummaryApi(mercadobitcoinApi):
    type = "day-summary"

    def _get_endpoint(self, date: datetime.date) -> str:
        return f"{self.base_endpoint}/{self.coin}/{self.type}/{date.year}/{date.month}/{date.day}"

class tradesApi(mercadobitcoinApi):     
    type = "trades"

    def _get_unix_epoch(self, date: datetime.datetime) -> int:
        return int(date.timestamp())

    def _get_endpoint(self, date_from: datetime.datetime = None, date_to: datetime.datetime = None) -> str:

        if date_from and not date_to:
            unix_date_from = self._get_unix_epoch(date_from)
            endpoint = f"{self.base_endpoint}/{self.coin}/{self.type}/{unix_date_from}"
        elif date_from and date_to:
            unix_date_from = self._get_unix_epoch(date_from)
            unix_date_to = self._get_unix_epoch(date_to)    
            endpoint = f"{self.base_endpoint}/{self.coin}/{self.type}/{unix_date_from}/{unix_date_to}"
        else:
            endpoint = f"{self.base_endpoint}/{self.coin}/{self.type}"       

        return endpoint

class dataTypeNotSupportedForIngestionException(Exception):

    def __init__(self, data):
        self.data = data
        self.message = f"Data type {type(data)} is not supported for ingestion"
        super().__init__(self.message)


class dataWriter:

    def __init__(self, coin: str, api: str) -> None:        
        self.api = api
        self.coin = coin
        self.filename = f"{self.api}/{self.coin}/{datetime.datetime.now()}.json"

    def _write_row(self, row: str) -> None:
        os.makedirs(os.path.dirname(self.filename), exist_ok=True)
        with open(self.filename, "a") as f:
            f.write(row)

    def write(self, data: [List, dict]):
        if isinstance(data, dict):
            self._write_row(json.dumps(data) + "\n")
        elif isinstance(data, List):
            for element in data:
                self.write(element)
        else:
            raise dataTypeNotSupportedForIngestionException(data)

class dataIngestor(ABC):

    def __init__(self, writer: dataWriter, coins: List[str], default_start_date: datetime.date):
        self.coins = coins
        self.default_start_date = default_start_date
        self.writer = writer
        self._checkpoint = None

    def _get_checkpoint(self):
        if not self._checkpoint:
            return self.default_start_date
        else:
            return self._checkpoint

    def _updete_checkpoint(self, value):
        self._checkpoint = value

    @abstractmethod
    def ingest(self) -> None:
        pass

class daySummaryIngestor(dataIngestor):

    def ingest(self) -> None:
        date = self._get_checkpoint()

        if date < datetime.date.today():
            for coin in self.coins:              
                api = daySummaryApi(coin=coin)
                data = api.get_data(date=date)
                self.writer(coin=coin, api=api.type).write(data)
                self._updete_checkpoint(date + datetime.timedelta(days=1))


ingestor = daySummaryIngestor(writer=dataWriter, coins=["BTC","ETH","LTC"], default_start_date=datetime.date(2021, 6, 1))

@repeat(every(1).seconds)
def job():
    ingestor.ingest()

while True:
    run_pending()
    time.sleep(0.5)