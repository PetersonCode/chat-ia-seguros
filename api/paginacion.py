from __future__ import annotations

from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class Paginador(PageNumberPagination):
    page_size = 25
    page_query_param = "pagina"
    page_size_query_param = None

    def get_paginated_response(self, data):
        return Response(
            {
                "total": self.page.paginator.count,
                "pagina": self.page.number,
                "por_pagina": self.page_size,
                "resultados": data,
            }
        )
