import { api } from "../api.js?v=20261105revision9";
import { inicializarNav } from "../nav.js?v=20261105revision9";
import { abrirRenovacion } from "../lib/renovacion.js?v=20261105revision9";
let puedeAprobar=false,personaActual=null,equipo=[];
const $=id=>document.getElementById(id);
const el=(tag,texto,clase='')=>{const n=document.createElement(tag);n.textContent=texto;n.className=clase;return n;};
const dinero=v=>Number(v).toLocaleString('es-AR',{style:'currency',currency:'ARS'});
function link(texto,url){const a=el('a',texto);a.href=url;return a;}
function boton(texto,fn){const tono=texto.startsWith('Cancelar')?'outline-danger':(['Completar','Marcar como enviado'].includes(texto)?'success':texto==='Renovar'?'renovar':'primary');const b=el('button',texto,`btn btn-sm btn-${tono} me-2`);b.type='button';b.onclick=async()=>{b.disabled=true;try{await fn();}catch(e){$('estado').textContent=e.mensaje??e.message;}finally{b.disabled=false;}};return b;}
function bloque(titulo,filas,render){const c=el('section','','col-lg-6');const card=el('div','','card h-100');card.append(el('h2',titulo,'card-header h5'));const lista=el('div','','card-body');if(!filas.length)lista.append(el('p','Sin pendientes.','text-muted'));let extra=null;if(filas.length>5){extra=el('details');extra.append(el('summary',`Ver otros ${filas.length-5}`,'small mb-2'));}for(const [i,f] of filas.entries()){const p=el('p');p.append(render(f));(i<5?lista:extra).append(p);}if(extra)lista.append(extra);card.append(lista);c.append(card);$('pendientes').append(c);}
async function cargar(){
    const d=await api.get('/api/gestion/inicio/');$('resumen').replaceChildren();$('pendientes').replaceChildren();
    const titulos={renovaciones:'Renovaciones en 30 días',morosos:'Pólizas con atraso',interesados:'Interesados por contactar',siniestros:'Siniestros sin movimiento · 7 días',sin_respuesta:'Chats esperando · 2 horas'};
    for(const [k,t] of Object.entries(titulos)){const c=el('div','','col-sm-6 col-xl');const card=el('div','',`card card-body h-100 indicador indicador-${k}`);card.append(el('span',t,'small text-muted'),el('strong',String(d.cantidades[k]),'h2 mb-0'));c.append(card);$('resumen').append(c);}
    bloque('Renovaciones próximas',d.renovaciones,p=>{const s=el('span');s.append(link(`${p.numero} · ${p.cliente} · ${p.patente} · vence ${p.vence}`,`/panel/cliente/?id=${p.cliente_id}`));if(puedeAprobar)s.append(boton('Renovar',()=>abrirRenovacion(p.id,async()=>{await cargar();await mensual();})));return s;});
    bloque('Cuotas atrasadas · primero las más antiguas',d.morosos,p=>link(`${p.poliza__numero_poliza} · ${p.poliza__cliente__nombre} ${p.poliza__cliente__apellido} · ${dinero(p.importe)} · desde ${p.desde}`,`/panel/cliente/?id=${p.poliza__cliente_id}`));
    bloque('Seguimiento de interesados',d.interesados,i=>link(`${i.nombre} · ${i.responsable} · ${i.fecha}`,`/panel/interesado/?id=${i.id}`));
    bloque('Siniestros sin movimiento',d.siniestros,s=>link(`${s.numero} · último movimiento ${s.desde.slice(0,10)}`,'/panel/siniestros/'));
    bloque('Clientes sin respuesta',d.sin_respuesta,c=>link(c.numero,`/panel/conversacion/?id=${c.id}`));
    $('automaticos').checked=d.automaticos;
    await Promise.all([tareas(),avisos(),cargarEncuestas()]);
}
async function cargarEncuestas(){
    const d=await api.get('/api/gestion/encuestas/');$('encuestas').replaceChildren();
    for(const r of d.resultados)$('encuestas').append(el('p',`${r.cliente} · ${r.numero} · ${r.puntaje}/5 · ${r.fecha.slice(0,10)}`));
    if(!d.total)$('encuestas').textContent='Todavía no hay respuestas.';
}
async function tareas(){
    const d=await api.get('/api/gestion/tareas/?mias='+($('mis-tareas').checked?'1':'0'));$('tareas').replaceChildren();
    for(const t of d.resultados){
        const c=el('article','','border-bottom py-3');c.append(el('strong',t.titulo),el('p',`${t.responsable} · ${t.vence} · ${t.detalle}`));
        if(t.cliente)c.append(link('Ver cliente',`/panel/cliente/?id=${t.cliente}`));
        if(puedeAprobar||[t.asignada_a,t.creada_por].includes(personaActual)){
            c.append(boton('Completar',async()=>{await api.patch(`/api/gestion/tareas/${t.id}/`,{accion:'hecha'});await tareas();}),boton('Cancelar tarea',async()=>{await api.patch(`/api/gestion/tareas/${t.id}/`,{accion:'cancelada'});await tareas();}));
            const s=el('select','','form-select form-select-sm my-2');s.setAttribute('aria-label',`Responsable de ${t.titulo}`);for(const f of equipo)s.add(new Option(f.nombre,f.id));s.value=t.asignada_a;
            c.append(s,boton('Reasignar',async()=>{await api.patch(`/api/gestion/tareas/${t.id}/`,{accion:'reasignar',asignada_a:Number(s.value)});await tareas();}));
        }
        $('tareas').append(c);
    }
    if(!d.total)$('tareas').append(el('p','No hay tareas pendientes.','text-muted'));
    if(d.total>d.resultados.length)$('tareas').append(el('p',`Mostrando las primeras ${d.resultados.length} de ${d.total}. Usá «Solo mis tareas» para acotar.`,'small text-muted'));
}
async function avisos(){const d=await api.get('/api/gestion/avisos/');$('avisos').replaceChildren();for(const a of d.resultados){const c=el('article','','border-bottom py-3');c.append(el('strong',`${a.tipo} · ${a.numero} · ${a.estado}`),el('p',a.texto));if(a.estado==='para_contactar'){const w=link('Abrir WhatsApp','https://wa.me/'+a.numero.replace(/\D/g,'')+'?text='+encodeURIComponent(a.texto));w.target='_blank';w.rel='noopener noreferrer';w.className='btn btn-whatsapp btn-sm me-2';c.append(w,boton('Marcar como enviado',async()=>{await api.post(`/api/gestion/avisos/${a.id}/resolver/`,{estado:'manual'});await avisos();}),boton('Cancelar',async()=>{await api.post(`/api/gestion/avisos/${a.id}/resolver/`,{estado:'cancelado'});await avisos();}));}$('avisos').append(c);}if(!d.resultados.length)$('avisos').append(el('p','No hay avisos pendientes.','text-muted'));}
$('nueva-tarea').onsubmit=async e=>{e.preventDefault();const b=e.target.querySelector('button[type=submit]')??e.target.querySelector('button');if(b.disabled)return;b.disabled=true;try{const d=Object.fromEntries(new FormData(e.target));d.cliente=d.cliente?Number(d.cliente):null;d.asignada_a=Number(d.asignada_a);await api.post('/api/gestion/tareas/',d);e.target.reset();await tareas();$('estado').textContent='Tarea asignada.';}catch(e){$('estado').textContent=e.mensaje??e.message;}finally{b.disabled=false;}};
$('buscar-cliente').onchange=async()=>{try{const d=await api.get('/api/clientes/?q='+encodeURIComponent($('buscar-cliente').value));$('cliente').replaceChildren(new Option('Tarea general',''));for(const c of d.resultados)$('cliente').add(new Option(`${c.nombre} ${c.apellido}`,c.id));}catch(e){$('estado').textContent=e.mensaje??e.message;}};
$('mis-tareas').onchange=tareas;
$('automaticos').onchange=async()=>{try{await api.patch('/api/gestion/config/',{automaticos:$('automaticos').checked});}catch(e){$('estado').textContent=e.mensaje??e.message;await cargar();}};
$('actualizar').onclick=async()=>{const b=$('actualizar');b.disabled=true;try{await api.post('/api/gestion/actualizar/',{});await cargar();$('estado').textContent='Avisos actualizados.';}catch(e){$('estado').textContent=e.mensaje??e.message;}finally{b.disabled=false;}};
inicializarNav();
async function mensual(){try{const d=await api.get('/api/gestion/reporte/?'+new URLSearchParams($('mes-reporte').value?{mes:$('mes-reporte').value}:{}));$('mes-reporte').value=d.mes;$('reporte').replaceChildren();for(const [k,t] of Object.entries({nuevas:'Pólizas nuevas',bajas:'Bajas registradas',renovadas:'Renovadas',cobrado:'Cobrado',comision:'Comisión sobre cobros'})){const c=el('div','','col-sm-6 col-xl');c.append(el('p',t,'small text-muted'),el('strong',d[k]===null?'Acceso restringido':(['cobrado','comision'].includes(k)?dinero(d[k]):String(d[k])),'h4'));$('reporte').append(c);}const aviso=el('p',`${d.sin_porcentaje} pólizas sin porcentaje de comisión informado.`,'small text-muted');$('reporte').append(aviso);}catch(e){$('estado').textContent=e.mensaje??e.message;}}
$('mes-reporte').onchange=mensual;
Promise.all([api.get('/api/auth/me/'),api.get('/api/funcionarios/')]).then(async([u,f])=>{
    puedeAprobar=u.puede_aprobar;personaActual=u.id;equipo=f.resultados;
    for(const p of f.resultados)$('asignada').add(new Option(p.nombre,p.id,p.id===personaActual,p.id===personaActual));
    $('configuracion').hidden=!u.puede_aprobar;await cargar();await mensual();
}).catch(e=>{$('estado').textContent=e.mensaje??e.message;});
