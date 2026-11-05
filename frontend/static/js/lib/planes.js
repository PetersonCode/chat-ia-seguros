import { api } from "../api.js?v=20261105fechas1";
const $=id=>document.getElementById(id);
const campos=['cubre','no_cubre','limites','asistencia'];
let planes=[],companias=[];
function opcion(select,texto,valor){const o=document.createElement('option');o.textContent=texto;o.value=valor;select.append(o);}
function nombrePlan(p){return `${companias.find(c=>c.id===p.compania_id)?.nombre??'Compañía'} · ${p.nombre} · v${p.version}${p.nivel?'':' (sin nivel)'}${p.activo?'':' (inactivo)'}`;}
async function cargar(){
    planes=[];let pagina=1;
    while(true){
        const d=await api.get('/api/planes-cobertura/?pagina='+pagina);
        planes.push(...d.resultados);if(pagina*d.por_pagina>=d.total)break;pagina++;
    }
    $('plan-editar').replaceChildren();opcion($('plan-editar'),'Nuevo plan','');
    for(const p of planes)opcion($('plan-editar'),nombrePlan(p),p.id);
}
export async function inicializarPlanes(puedeEditar,listaCompanias,opciones={}){
    if(!puedeEditar)return;
    companias=listaCompanias;
    await cargar();
    $('plan-compania').replaceChildren();opcion($('plan-compania'),'Elegí la compañía','');
    for(const c of companias)opcion($('plan-compania'),c.nombre,c.id);
    $('gestionar-planes').hidden=false;
    $('plan-editar').onchange=()=>{
        const p=planes.find(x=>String(x.id)===$('plan-editar').value);
        for(const k of ['nombre','compania_id','nivel',...campos])$('form-plan').elements[k].value=p?.[k]??'';
        $('plan-compania').disabled=Boolean(p);$('plan-activo').checked=p?.activo??true;
        $('estado-plan').textContent=p?`Editando versión ${p.version}. Los contratos existentes conservarán su copia.`:'';
        $('eliminar-plan').hidden=!(opciones.esAdministrador&&p);
    };
    $('eliminar-plan').hidden=true;
    $('eliminar-plan').onclick=()=>{
        const p=planes.find(x=>String(x.id)===$('plan-editar').value);if(!p)return;
        opciones.confirmarEliminacion(`Eliminar el plan ${p.nombre}`,
            'Se borra el plan. Las pólizas que lo usaban conservan sus condiciones como condiciones particulares. No se puede deshacer.',
            async()=>{await api.post(`/api/planes-cobertura/${p.id}/eliminar/`,{});await opciones.alEliminar?.(p.nombre);});
    };
    $('form-plan').onsubmit=async e=>{
        e.preventDefault();$('guardar-plan').disabled=true;
        const datos={...Object.fromEntries(new FormData($('form-plan'))),compania_id:Number($('plan-compania').value),activo:$('plan-activo').checked};
        try{
            const id=$('plan-editar').value;
            const p=id?await api.patch(`/api/planes-cobertura/${id}/`,datos):await api.post('/api/planes-cobertura/',datos);
            await cargar();$('plan-editar').value=p.id;$('plan-compania').disabled=true;
            $('estado-plan').textContent=`Plan guardado, versión ${p.version}. Ya podés elegirlo en las pólizas de esta compañía.`;
        }catch(e){$('estado-plan').textContent=e.mensaje??e.message;}finally{$('guardar-plan').disabled=false;}
    };
}
