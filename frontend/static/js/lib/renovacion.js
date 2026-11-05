<<<<<<< HEAD
import { api } from "../api.js?v=20261105revision10";
=======
import { api } from "../api.js?v=20261105burbujas1";
>>>>>>> origin/main
export async function abrirRenovacion(id,alGuardar=()=>{}){
    const p=await api.get(`/api/polizas/${id}/`);
    const dialogo=document.createElement('dialog');dialogo.className='dialog-accion';
    dialogo.append(document.getElementById('plantilla-renovacion').content.cloneNode(true));
    dialogo.querySelector('h2').textContent=`Renovar ${p.numero_poliza}`;
    const inicio=new Date(p.fecha_vencimiento+'T00:00:00Z');inicio.setUTCDate(inicio.getUTCDate()+1);
    const duracion=new Date(p.fecha_vencimiento+'T00:00:00Z')-new Date(p.fecha_inicio+'T00:00:00Z');
    const fin=new Date(inicio.getTime()+duracion);
    dialogo.querySelector('[data-resumen]').textContent=`Nueva vigencia desde ${inicio.toISOString().slice(0,10)}. Revisá las fechas, el precio y las condiciones antes de confirmar.`;
    const form=dialogo.querySelector('form');form.elements.fecha_vencimiento.value=fin.toISOString().slice(0,10);form.elements.fecha_vencimiento.min=inicio.toISOString().slice(0,10);
    dialogo.querySelector('[data-cerrar]').onclick=()=>dialogo.close();dialogo.onclose=()=>dialogo.remove();
    form.onsubmit=async e=>{e.preventDefault();const boton=form.querySelector('button[type="submit"]')??form.querySelector('button.btn-primary');boton.disabled=true;try{await api.post(`/api/gestion/polizas/${id}/renovar/`,{prima_mensual:form.elements.prima_mensual.value,fecha_vencimiento:form.elements.fecha_vencimiento.value,conservar_condiciones:form.elements.conservar_condiciones.checked});dialogo.close();await alGuardar();}catch(e){dialogo.querySelector('[data-error]').textContent=e.mensaje??e.message;}finally{boton.disabled=false;}};
    document.body.append(dialogo);dialogo.showModal();
}
