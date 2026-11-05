import { api } from '../api.js?v=20261105burbujas1';
import { fusionarMensajes } from './mensajes.js?v=20261105burbujas1';
import { formatearFechaHora } from './formato.js?v=20261105burbujas1';
import { crearTarjetaAdjunto, esMarcadorDeArchivo } from './adjuntos.js?v=20261105burbujas1';

// Solo referencias y borradores por usuario; nunca se almacena el historial.
const PREFIJO = 'castano.chat.';
export function leerEstadoChat(valor) {
    try {
        const s = JSON.parse(valor);
        return Number.isSafeInteger(s?.id) && s.id > 0 && ['normal','ampliado','minimizado'].includes(s.modo) ? s : null;
    } catch { return null; }
}
export function puedeResponderChat(c, usuario) {
    return c?.estado === 'abierta' && c.modo === 'humano' && c.atendida_por?.id === usuario.id && Boolean(c.ventana_24h_abierta);
}

function nodo(tag, texto='', clase='') {
    const n=document.createElement(tag); n.textContent=texto; n.className=clase; return n;
}
function guardar(clave, valor) { try { valor===null ? sessionStorage.removeItem(clave) : sessionStorage.setItem(clave,valor); } catch { /* La sesión puede bloquear almacenamiento. */ } }
function leer(clave) { try { return sessionStorage.getItem(clave); } catch { return null; } }

export async function iniciarChatFlotante() {
    if (document.getElementById('chat-flotante') || location.pathname==='/') return;
    const usuario=await api.get('/api/auth/me/');
    const clave=PREFIJO+usuario.id;
    let estado=leerEstadoChat(leer(clave)), detalle=null, mensajes=[], cargando=false, version=0, nuevos=0;
    const caja=nodo('section','','chat-flotante'); caja.id='chat-flotante'; caja.hidden=true;
    caja.setAttribute('aria-label','Chat de atención flotante');
    const cabecera=nodo('header','','chat-flotante-cabecera');
    const titulo=nodo('button','Chat de atención','chat-flotante-titulo'); titulo.type='button';
    const minimizar=nodo('button','−','chat-flotante-control'); minimizar.type='button'; minimizar.setAttribute('aria-label','Minimizar chat');
    const ampliar=nodo('button','⤢','chat-flotante-control'); ampliar.type='button'; ampliar.setAttribute('aria-label','Ampliar chat');
    const cerrar=nodo('button','×','chat-flotante-control'); cerrar.type='button'; cerrar.setAttribute('aria-label','Cerrar ventana del chat'); cerrar.title='Cerrar la ventana no devuelve la conversación al bot';
    cabecera.append(titulo,minimizar,ampliar,cerrar);
    const cuerpo=nodo('div','','chat-flotante-cuerpo');
    const barra=nodo('div','','chat-flotante-barra');
    const situacion=nodo('p','','small mb-1');
    const tomar=nodo('button','Tomar conversación','btn btn-primary btn-sm'); tomar.type='button';
    const ficha=nodo('a','Ver detalle completo','btn btn-outline-secondary btn-sm'); ficha.dataset.chatCompleto='true';
    barra.append(situacion,tomar,ficha);
    const lista=nodo('div','','chat-flotante-mensajes'); lista.setAttribute('aria-label','Mensajes de la conversación');
    const aviso=nodo('p','','chat-flotante-aviso small'); aviso.setAttribute('role','status');
    const form=nodo('form','','chat-flotante-respuesta');
    const label=nodo('label','Respuesta al cliente','form-label'); label.htmlFor='chat-flotante-texto';
    const texto=nodo('textarea','','form-control'); texto.id='chat-flotante-texto'; texto.rows=2; texto.maxLength=4000; texto.required=true;
    const enviar=nodo('button','Enviar','btn btn-success mt-2'); enviar.type='submit';
    form.append(label,texto,enviar); cuerpo.append(barra,lista,aviso,form); caja.append(cabecera,cuerpo); document.body.append(caja);
    function borrador() { return `${clave}.borrador.${estado.id}`; }
    function pintarModo() {
        caja.hidden=!estado;
        if(!estado)return;
        caja.dataset.modo=estado.modo; cuerpo.hidden=estado.modo==='minimizado';
        titulo.setAttribute('aria-expanded',String(estado.modo!=='minimizado'));
        titulo.textContent=(detalle?.cliente_info ? `${detalle.cliente_info.nombre} ${detalle.cliente_info.apellido}` : detalle?.whatsapp??'Chat de atención')+(nuevos?` · ${nuevos} nuevos`:'');
        ampliar.setAttribute('aria-label',estado.modo==='ampliado'?'Reducir chat':'Ampliar chat');
        guardar(clave,JSON.stringify(estado));
    }
    function modo(m) { if(estado){estado.modo=m;if(m!=='minimizado')nuevos=0;pintarModo();} }
    ficha.onclick=e=>{
        if(e.button===0&&!e.ctrlKey&&!e.metaKey&&!e.shiftKey&&!e.altKey)modo('minimizado');
    };
    async function actualizar() {
        if(!estado || cargando || document.hidden)return;
        cargando=true; const turno=version, id=estado.id;
        try {
            const [d,r]=await Promise.all([api.get(`/api/conversaciones/${id}/`),api.get(`/api/conversaciones/${id}/mensajes/?despues_de=${mensajes.at(-1)?.id??0}`)]);
            if(turno!==version)return;
            const antes=new Set(mensajes.map(m=>m.id));
            if(mensajes.length && estado.modo==='minimizado')nuevos+=r.mensajes.filter(m=>m.emisor==='cliente'&&!antes.has(m.id)).length;
            detalle=d; mensajes=fusionarMensajes(mensajes,r.mensajes);
            const abajo=lista.scrollHeight-lista.scrollTop-lista.clientHeight<65;
            lista.replaceChildren(...mensajes.map(m=>{
                const item=nodo('article','','mensaje-chat '+(m.emisor==='cliente'?'msg-cliente':'msg-saliente'));
                item.append(nodo('p',`${m.emisor==='cliente'?'Cliente':m.emisor==='bot'?'Bot':'Asesor'} · ${formatearFechaHora(m.fecha_hora)} · ${m.estado_envio}`,'small text-muted mb-1'),...(m.adjunto?[crearTarjetaAdjunto(m.adjunto)]:[]),...(esMarcadorDeArchivo(m)?[]:[nodo('p',m.texto??'','mb-0')]));
                if(m.estado_envio==='retenido')item.classList.add('msg-retenido');return item;
            }));
            if(abajo || antes.size===0)lista.scrollTop=lista.scrollHeight;
            situacion.textContent=`${d.estado} · ${d.modo==='humano'?'Atiende: '+(d.atendida_por?.nombre??'equipo'):'Atención del bot'}`;
            tomar.hidden=d.estado!=='abierta';
            tomar.textContent=d.modo==='humano'&&d.atendida_por?.id===usuario.id?'Devolver al bot':'Tomar conversación';
            form.hidden=!puedeResponderChat(d,usuario);
            aviso.textContent=d.estado==='cerrada'?'Conversación cerrada: solo consulta.':!d.ventana_24h_abierta?'La ventana de WhatsApp está cerrada.':form.hidden?'Tomá la conversación para responder.':'';
            pintarModo();
        } catch(e) { if(turno===version)aviso.textContent=e.mensaje??'No se pudo actualizar el chat. Se reintentará.'; }
        finally { cargando=false; }
    }
    function abrir(id) {
        if(estado?.id!==id){version++;detalle=null;mensajes=[];lista.replaceChildren();estado={id,modo:'normal'};texto.value=leer(borrador())??'';}
        else estado.modo='normal';
        nuevos=0;ficha.href=`/panel/conversacion/?id=${id}`;pintarModo();actualizar();
    }
    titulo.onclick=()=>modo(estado?.modo==='minimizado'?'normal':'minimizado');
    minimizar.onclick=()=>modo('minimizado'); ampliar.onclick=()=>modo(estado?.modo==='ampliado'?'normal':'ampliado');
    cerrar.onclick=()=>{version++;estado=null;detalle=null;mensajes=[];guardar(clave,null);pintarModo();};
    texto.oninput=()=>{if(estado)guardar(borrador(),texto.value);};
    function notificarCambio(id) {
        document.dispatchEvent(new CustomEvent('castano:chat-actualizado',{detail:{id}}));
        document.dispatchEvent(new Event('pendientes:actualizar'));
    }
    tomar.onclick=async()=>{const id=estado.id,accion=detalle?.modo==='humano'&&detalle.atendida_por?.id===usuario.id?'devolver':'tomar';tomar.disabled=true;try{await api.post(`/api/conversaciones/${id}/${accion}/`,{});await actualizar();notificarCambio(id);}catch(e){aviso.textContent=e.mensaje??e.message;}finally{tomar.disabled=false;}};
    form.onsubmit=async e=>{
        e.preventDefault();if(!estado||!puedeResponderChat(detalle,usuario)||!texto.value.trim())return;
        const id=estado.id, draft=borrador(), contenido=texto.value; enviar.disabled=true;
        try{await api.post(`/api/conversaciones/${id}/responder/`,{texto:contenido.trim()});guardar(draft,null);if(estado?.id===id){texto.value='';await actualizar();}notificarCambio(id);}
        catch(e){aviso.textContent=e.mensaje??e.message;}finally{enviar.disabled=false;}
    };
    document.addEventListener('click',e=>{
        if(e.defaultPrevented||e.button!==0||e.ctrlKey||e.metaKey||e.shiftKey||e.altKey)return;
        const a=e.target.closest('a[href]');if(!a||a.dataset.chatCompleto||a.target==='_blank')return;
        const url=new URL(a.href,location.href),id=Number(url.searchParams.get('id'));
        if(url.origin===location.origin&&url.pathname==='/panel/conversacion/'&&Number.isSafeInteger(id)&&id>0){e.preventDefault();abrir(id);}
    });
    if(location.pathname==='/panel/conversacion/'){
        const id=Number(new URLSearchParams(location.search).get('id'));
        if(Number.isSafeInteger(id)&&id>0){const b=nodo('button','Abrir chat flotante','btn btn-primary btn-sm');b.type='button';b.onclick=()=>abrir(id);document.querySelector('main > header')?.append(b);}
    }
    if(estado){const previo=estado;estado=null;abrir(previo.id);modo(previo.modo);}
    setInterval(actualizar,5000);
}

if(typeof document!=='undefined')iniciarChatFlotante().catch(()=>{});
