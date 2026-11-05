<<<<<<< HEAD
import { api } from "../api.js?v=20261105revision10";
=======
import { api } from "../api.js?v=20261105burbujas1";
>>>>>>> origin/main
export async function iniciarFidelizacion(id){
    const c=document.createElement('section');c.className='card mb-3';
    c.append(document.getElementById('plantilla-fidelizacion').content.cloneNode(true));
    document.querySelector('main').append(c);
    const perfil=c.querySelector('[data-perfil]'),referido=c.querySelector('[data-referido]'),estado=c.querySelector('[data-estado]'),lista=c.querySelector('[data-lista]');
    const me=await api.get('/api/auth/me/');
    async function cargar(){const p=await api.get(`/api/gestion/clientes/${id}/perfil/`);perfil.elements.nacimiento.value=p.nacimiento??'';perfil.elements.comerciales.checked=p.comerciales;for(const e of perfil.elements)e.disabled=!me.puede_aprobar;referido.hidden=!me.puede_aprobar;lista.replaceChildren();for(const r of p.referidos){const div=document.createElement('article'),parrafo=document.createElement('p');parrafo.textContent=`${r.cliente} · ${r.estado} · ${r.beneficio}`;div.append(parrafo);if(r.estado==='pendiente'&&me.puede_aprobar){const d=document.createElement('input');d.className='form-control mb-2';d.placeholder='Beneficio entregado o motivo de cancelación';d.setAttribute('aria-label','Detalle del beneficio');d.maxLength=1000;div.append(d);for(const [etiqueta,valor] of [['Confirmar beneficio','otorgado'],['Cancelar','cancelado']]){const b=document.createElement('button');b.type='button';b.className='btn btn-sm btn-outline-primary me-2';b.textContent=etiqueta;b.onclick=async()=>{b.disabled=true;try{await api.patch(`/api/gestion/referidos/${r.id}/`,{estado:valor,beneficio:d.value});await cargar();}catch(e){estado.textContent=e.mensaje??e.message;}finally{b.disabled=false;}};div.append(b);}}lista.append(div);}}
    perfil.onsubmit=async e=>{e.preventDefault();try{await api.patch(`/api/gestion/clientes/${id}/perfil/`,{nacimiento:perfil.elements.nacimiento.value||null,comerciales:perfil.elements.comerciales.checked});estado.textContent='Preferencias guardadas.';}catch(e){estado.textContent=e.mensaje??e.message;}};
    c.querySelector('#buscar-referido').onchange=async e=>{try{const d=await api.get('/api/clientes/?q='+encodeURIComponent(e.target.value));referido.elements.referido.replaceChildren(new Option('Elegí un cliente',''));for(const p of d.resultados)if(p.id!==Number(id))referido.elements.referido.add(new Option(`${p.nombre} ${p.apellido}`,p.id));}catch(e){estado.textContent=e.mensaje??e.message;}};
    referido.onsubmit=async e=>{e.preventDefault();try{await api.post(`/api/gestion/clientes/${id}/referidos/`,{referido:Number(referido.elements.referido.value)});await cargar();estado.textContent='Referido registrado. El beneficio queda pendiente de confirmación; no se alteran cuotas automáticamente.';}catch(e){estado.textContent=e.mensaje??e.message;}};
    try{await cargar();}catch(e){estado.textContent=e.mensaje??e.message;}
}
