from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from django.db import close_old_connections, connection, transaction
from datos import fabricas
from datos.models import Cotizacion
from datos.tests.transacciones import PruebaConTransacciones
from negocio.cotizaciones import cargar_cotizacion, elegir_cotizacion


class EleccionConcurrenteTests(PruebaConTransacciones):
    def test_dos_asesores_eligen_alternativas_del_mismo_interesado(self):
        fabricas.crear_catalogos()
        asesor=fabricas.crear_funcionario('Diego')
        compania=fabricas.crear_compania()
        interesado=fabricas.crear_interesado()
        opciones=[cargar_cotizacion(asesor.id,compania.id,'intermedia',importe,interesado_id=interesado.id)
                  for importe in ('15000','18000')]
        elegir_cotizacion(opciones[0].id,asesor.id)
        empezar=Barrier(2)
        def elegir(id):
            close_old_connections()
            try:
                with transaction.atomic():
                    with connection.cursor() as cursor:
                        cursor.execute("SET LOCAL lock_timeout = '5s'")
                    empezar.wait(timeout=5)
                    return elegir_cotizacion(id,asesor.id).id
            finally:
                connection.close()
        with ThreadPoolExecutor(max_workers=2) as equipo:
            resultados=list(equipo.map(elegir,[opciones[0].id,opciones[1].id]))
        self.assertCountEqual(resultados,[opciones[0].id,opciones[1].id])
        self.assertEqual(Cotizacion.objects.filter(interesado=interesado,elegida=True).count(),1)
