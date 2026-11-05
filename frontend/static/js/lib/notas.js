import { api } from "../api.js?v=20261105revision10";
export function iniciarNotas(id){
    const seccion=document.createElement('section');seccion.className='card mb-3';
    const titulo=document.createElement('h2');titulo.className='card-header h5';titulo.textContent='Notas internas del equipo';
    const cuerpo=document.createElement('div');cuerpo.className='card-body';
    const ayuda=document.createElement('p');ayuda.textContent='Solo las ve el equipo; no se envían al cliente ni se usan como condiciones del seguro.';ayuda.className='small text-muted';
    const form=document.createElement('form'),label=document.createElement('label'),entrada=document.createElement('textarea'),b=document.createElement('button'),lista=document.createElement('div'),estado=document.createElement('p');
    label.textContent='Nueva nota';label.htmlFor='nota-interna';label.className='form-label';entrada.id='nota-interna';entrada.className='form-control mb-2';entrada.required=true;entrada.minLength=3;entrada.maxLength=2000;b.textContent='Guardar nota';b.className='btn btn-outline-primary';estado.setAttribute('role','status');form.append(label,entrada,b);cuerpo.append(ayuda,form,estado,lista);seccion.append(titulo,cuerpo);document.querySelector('main').append(seccion);
    function pintar(d){lista.replaceChildren();for(const n of d.resultados){const p=document.createElement('p');p.className='border-top mt-3 pt-2';p.textContent=`${n.autor} · ${n.fecha.slice(0,10)}: ${n.texto}`;lista.append(p);}}
    form.onsubmit=async e=>{e.preventDefault();b.disabled=true;try{pintar(await api.post(`/api/gestion/clientes/${id}/notas/`,{texto:entrada.value}));entrada.value='';estado.textContent='Nota guardada.';}catch(e){estado.textContent=e.mensaje??e.message;}finally{b.disabled=false;}};
    api.get(`/api/gestion/clientes/${id}/notas/`).then(pintar).catch(e=>{estado.textContent=e.mensaje??e.message;});
}
