from pydantic import Field

from src.dao.yande_data_dao import YandeDataRepository


class QueryParams(YandeDataRepository.YandeDataQueryParams):
    ...
