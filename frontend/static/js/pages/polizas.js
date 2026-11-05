import { api } from "../api.js?v=20261104gestion2";
import { inicializarNav } from "../nav.js?v=20261104flotante1";
const $=id=>document.getElementById(id);
let pagina=1,total=0,elegida=null,puedeEditar=false,turno=0;
let planes=[],companias=[],planVersion=null;
const campos=['cubre','no_cubre','limites','asistencia'];
function nodo(tag,texto){const n=document.createElement(tag);n.textContent=texto;return n;}
async function todos(ruta){
    const filas=[];let p=1;
    while(true){const d=await api.get(ruta+(ruta.includes('?')?'&':'?')+'pagina='+p);filas.push(...d.resultados);if(!d.por_pagina||p*d.por_pagina>=d.total)return filas;p++;}
}
function opcion(select,texto,valor){const o=nodo('option',texto);o.value=valor;select.append(o);}
function nombrePlan(p){return `${companias.find(c=>c.id===p.compania_id)?.nombre??'Compañía'} · ${p.nombre} · v${p.version}${p.activo?'':' (inactivo)'}`;}
async function cargar(){
    const actual=++turno;
    $('estado').textContent='Cargando pólizas…';
    try{
        const d=await api.get('/api/polizas/?'+new URLSearchParams({q:$('busqueda').value,pagina}));
        if(actual!==turno)return;
        total=d.total;$('filas').replaceChildren();
        for(const p of d.resultados){
            const tr=nodo('tr','');
            for(const v of [p.numero,p.cliente,p.patente,p.compania,p.estado])tr.append(nodo('td',v||'—'));
            const td=nodo('td',''),b=nodo('button',puedeEditar?'Ver / cargar cobertura':'Ver cobertura');
            const ficha=nodo('a','Ficha del cliente');ficha.href=`/panel/cliente/?id=${p.cliente_id}`;
            ficha.className='btn btn-sm btn-outline-secondary ms-2';
            b.className='btn btn-sm btn-outline-primary';b.onclick=()=>abrir(p);td.append(b,ficha);tr.append(td);$('filas').append(tr);
        }
        $('estado').textContent=total?`${total} ${total===1?'póliza':'pólizas'}`:'No hay pólizas con esa búsqueda.';
        $('pagina').textContent=`Página ${pagina}`;$('anterior').disabled=pagina<=1;$('siguiente').disabled=pagina*d.por_pagina>=total;
    }catch(e){$('estado').textContent=e.mensaje??e.message;}
}
async function abrir(p){
    elegida=p;$('titulo-condiciones').textContent=`${p.numero} · ${p.compania} · ${p.patente||p.cliente}`;
    $('error').textContent='';$('guardar').hidden=!puedeEditar;
    try{
        const d=await api.get(`/api/polizas/${p.id}/condiciones/`);
        for(const campo of campos){
            const e=$('condiciones').elements[campo];e.value=d[campo]??'';e.readOnly=!puedeEditar;
        }
        $('elegir-plan').replaceChildren();opcion($('elegir-plan'),'Condiciones particulares / sin plan','');
        for(const plan of planes.filter(x=>x.compania_id===p.compania_id&&(x.activo||x.id===d.plan_id)))opcion($('elegir-plan'),nombrePlan(plan),plan.id);
        $('elegir-plan').value=d.plan_id??'';$('elegir-plan').disabled=!puedeEditar;
        $('aplicar-plan').hidden=!puedeEditar;$('aplicar-plan').disabled=!$('elegir-plan').value;
        planVersion=d.plan_version;
        $('version-plan').textContent=d.plan_id?`Esta póliza conserva la versión ${d.plan_version} confirmada. Volvé a elegir el plan si querés aplicar su versión actual.`:'Podés cargar condiciones particulares sin usar un plan.';
        $('editar-condiciones').showModal();
    }catch(e){$('estado').textContent=e.mensaje??e.message;}
}
$('buscar-polizas').onsubmit=e=>{e.preventDefault();pagina=1;cargar();};
$('anterior').onclick=()=>{pagina--;cargar();};$('siguiente').onclick=()=>{pagina++;cargar();};
$('cancelar').onclick=()=>$('editar-condiciones').close();
$('elegir-plan').onchange=()=>{
    const plan=planes.find(p=>String(p.id)===$('elegir-plan').value);
    planVersion=plan?.version??null;
    $('aplicar-plan').disabled=!plan;
    if(plan)for(const campo of campos)$('condiciones').elements[campo].value=plan[campo];
    $('version-plan').textContent=plan?'Datos del plan completados. Revisá suma asegurada, franquicia y excepciones de este contrato antes de guardar.':'Se conservará una copia particular de los campos que ves.';
};
$('aplicar-plan').onclick=()=>$('elegir-plan').onchange();
$('condiciones').onsubmit=async e=>{
    e.preventDefault();if(!puedeEditar)return;
    $('guardar').disabled=true;
    try{
        await api.patch(`/api/polizas/${elegida.id}/condiciones/`,{...Object.fromEntries(new FormData($('condiciones'))),
            plan_id:Number($('elegir-plan').value)||null,plan_version:planVersion});
        $('editar-condiciones').close();$('estado').textContent='Condiciones guardadas y disponibles para el bot. Si el chat está en modo humano, devolvelo al bot para probar.';
    }catch(e){$('error').textContent=e.mensaje??e.message;}finally{$('guardar').disabled=false;}
};
inicializarNav();
api.get('/api/auth/me/').then(async u=>{
    puedeEditar=Boolean(u.puede_aprobar);
    [planes,companias]=await Promise.all([todos('/api/planes-cobertura/'),todos('/api/companias/?activas=1')]);
    cargar();
})
    .catch(e=>{$('estado').textContent=e.mensaje??e.message;});
