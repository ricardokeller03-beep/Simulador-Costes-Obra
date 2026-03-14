# Simulador de Presupuesto de Obra

Herramienta interactiva para simular variaciones en presupuestos de obra de cimentaciones especiales.

## Funcionalidades

- **Carga automática** de ficheros .xlsm/.xlsx con estructura estándar de hoja COSTOS
- **Vista dual**: Presupuesto original (fijo) vs Simulado (editable)
- **Variables encadenadas**: ML → mediciones, Rendimiento × Máquinas → días → costes temporales
- **Drivers automáticos**: Tiempo, Medición, Partida Alzada, % sobre Producción
- **KPIs en tiempo real**: % Margen Bruto, Coste Directo, Producción
- **Resumen comparativo** por capítulo con desviaciones

## Uso local

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Despliegue en Streamlit Cloud

1. Sube este directorio a un repositorio GitHub
2. Ve a [share.streamlit.io](https://share.streamlit.io)
3. Conecta el repo y selecciona `app.py`
4. Deploy

## Estructura del Excel esperada

La hoja COSTOS debe tener:
- **Fila 8**: Nº Equipos
- **Fila 9**: Total Obra (ML)
- **Fila 10**: Rendimiento/día
- **Filas 21-35**: Personal
- **Filas 53-66**: Armadura
- **Filas 69-73**: Cemento
- **Filas 76-90**: Materiales
- **Filas 95-107**: Subcontrata
- **Filas 109-115**: Maquinaria Externa
- **Filas 125-133**: Otros Alquileres
- **Filas 137-152**: Consumibles/Parque
- **Filas 156-167**: Gastos Varios
- **Fila 172**: Gasoil
- **Fila 176**: Transportes
- **Fila 180**: Maquinaria Interna
- **Fila 184**: TOTAL COSTO DIRECTO
- **Filas 188-210**: Producción
- **Fila 211**: SUMA PRODUCCIÓN
