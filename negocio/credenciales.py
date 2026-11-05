"""Credencial descargable dibujada con Pillow, sin servicios externos."""
from io import BytesIO
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont

FUENTE=Path(__file__).with_name('fonts')/'DejaVuSans.ttf'

def _fuente(tamano):
    return ImageFont.truetype(str(FUENTE),size=tamano)

def _lineas(texto,fuente,ancho):
    lineas=[];actual=''
    for letra in str(texto):
        if fuente.getlength(actual+letra)>ancho:
            lineas.append(actual);actual=letra
        else:actual+=letra
    if actual:lineas.append(actual)
    return lineas or ['—']

def imagen_credencial(filas,fecha):
    imagen=Image.new('RGB',(1080,1240),'#0a2342');d=ImageDraw.Draw(imagen)
    titulo=_fuente(44);label=_fuente(24)
    d.rounded_rectangle((32,32,1048,1208),radius=30,fill='#12315c',outline='#35587f',width=2)
    d.text((78,75),'Seguros Castaño',font=titulo,fill='#ffffff')
    d.text((78,136),'CREDENCIAL DE CONTACTO',font=label,fill='#a9c8f2')
    y=205
    for k,v in filas.items():
        d.text((78,y),k.upper(),font=label,fill='#a9b8cf')
        for tamano in range(40,22,-1):
            valor=_fuente(tamano);lineas=_lineas(v,valor,924)
            if len(lineas)*(tamano+3)<=82:break
        limite=max(1,82//(tamano+3))
        if len(lineas)>limite:lineas=lineas[:limite];lineas[-1]=lineas[-1][:-1]+'…'
        for i,linea in enumerate(lineas):
            d.text((78,y+34+i*(tamano+3)),linea,font=valor,fill='#eef3fa')
        y+=120
    d.line((78,1105,1002,1105),fill='#35587f',width=2)
    for i,linea in enumerate(['Información de contacto y referencia del contrato.',
                             'Conservá el certificado de tu compañía.',f'Generada el {fecha:%d/%m/%Y}']):
        d.text((78,1120+i*25),linea,font=_fuente(20),fill='#a9b8cf')
    archivo=BytesIO();imagen.save(archivo,format='PNG',optimize=True);return archivo.getvalue()
