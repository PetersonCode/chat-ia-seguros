import test from 'node:test';
import assert from 'node:assert/strict';
import {plazoVencimiento,enlaceRecordatorio} from '../static/js/lib/vencimientos.js';

test('plazos de vencimiento distinguen hoy, mañana y fechas vencidas', () => {
    assert.equal(plazoVencimiento(7),'Vence en 7 días');
    assert.equal(plazoVencimiento(1),'Vence mañana');
    assert.equal(plazoVencimiento(0),'Vence hoy');
    assert.equal(plazoVencimiento(-1),'Venció hace 1 día');
});
test('enlace manual codifica el texto y acepta solo números internacionales', () => {
    assert.equal(enlaceRecordatorio('+5491100009001','Saldo: $5'), 'https://wa.me/5491100009001?text=Saldo%3A%20%245');
    assert.equal(enlaceRecordatorio('javascript:alert(1)','texto'),null);
    assert.equal(enlaceRecordatorio(null,'texto'),null);
});
