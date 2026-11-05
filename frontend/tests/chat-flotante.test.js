import { test } from 'node:test';
import assert from 'node:assert/strict';
import { leerEstadoChat, puedeResponderChat } from '../static/js/lib/chat-flotante.js';

test('restaura solo una referencia de conversación y un modo válido',()=>{
    assert.deepEqual(leerEstadoChat('{"id":19,"modo":"minimizado"}'),{id:19,modo:'minimizado'});
    for(const s of ['null','{}','no json','{"id":-1,"modo":"normal"}','{"id":"19","modo":"normal"}','{"id":1,"modo":"otro"}'])assert.equal(leerEstadoChat(s),null);
});
test('el envío requiere conversación abierta, propia, humana y con ventana',()=>{
    const c={estado:'abierta',modo:'humano',atendida_por:{id:4},ventana_24h_abierta:true};
    assert.equal(puedeResponderChat(c,{id:4}),true);
    assert.equal(puedeResponderChat(c,{id:5}),false);
    for(const d of [{estado:'cerrada'},{modo:'bot'},{ventana_24h_abierta:false},{atendida_por:null}])assert.equal(puedeResponderChat({...c,...d},{id:4}),false);
});
