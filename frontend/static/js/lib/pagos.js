import { api } from '../api.js?v=20261105revision9';
import { formatearFecha, formatearMonto } from './formato.js?v=20261105revision9';

/** Cobra la cuota más antigua con los mismos datos que valida el servidor. */
export async function abrirRegistroPago(poliza, alGuardar) {
    const actual = await api.get(`/api/polizas/${poliza.id}/`);
    const cuota = (actual.cuotas ?? [])
        .filter(c => ['pendiente', 'vencida'].includes(c.estado))
        .sort((a,b) => a.periodo.localeCompare(b.periodo) || a.id-b.id)[0];
    if (!cuota) throw new Error('Esta póliza no tiene cuotas pendientes de cobro.');
    const d=document.createElement('dialog');d.className='dialog-accion';
    const f=document.createElement('form');f.className='p-4';
    const titulo=document.createElement('h2');titulo.className='h5';titulo.textContent=`Registrar pago · ${actual.numero_poliza}`;
    const detalle=document.createElement('p');detalle.textContent=`Cuota del ${formatearFecha(cuota.periodo)}, vence el ${formatearFecha(cuota.vencimiento)}. Importe a registrar: ${formatearMonto(cuota.importe)}. Confirmá solo después de comprobar el cobro.`;
    const label=document.createElement('label');label.className='form-label';label.htmlFor='pago-referencia';label.textContent='Referencia del comprobante';
    const referencia=document.createElement('input');referencia.id='pago-referencia';referencia.name='referencia';referencia.className='form-control mb-3';referencia.required=true;referencia.maxLength=100;
    const aviso=document.createElement('p');aviso.setAttribute('role','alert');aviso.className='small text-danger';
    const cancelar=document.createElement('button');cancelar.type='button';cancelar.className='btn btn-outline-secondary me-2';cancelar.textContent='Cancelar';cancelar.onclick=()=>d.close();
    const guardar=document.createElement('button');guardar.type='submit';guardar.className='btn btn-success';guardar.textContent='Confirmar cobro';
    f.append(titulo,detalle,label,referencia,aviso,cancelar,guardar);d.append(f);document.body.append(d);d.onclose=()=>d.remove();d.showModal();
    f.onsubmit=async e=>{
        e.preventDefault();if(guardar.disabled)return;
        if(!referencia.value.trim()){aviso.textContent='Ingresá la referencia del comprobante.';return;}
        guardar.disabled=true;cancelar.disabled=true;aviso.textContent='';
        let resultado;
        try{resultado=await api.post(`/api/polizas/${poliza.id}/pagos/`,{referencia:referencia.value.trim(),importe:cuota.importe});}
        catch(e){aviso.textContent=e.mensaje??e.message??'No se pudo registrar el cobro.';guardar.disabled=false;cancelar.disabled=false;return;}
        d.close();await alGuardar?.(resultado);
    };
}
