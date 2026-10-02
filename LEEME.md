# Monitor de mercado (actualización diaria automática)

Tablero web que se regenera solo cada día hábil con precios de acciones del S&P 500, ETFs, ETFs de bonos, futuros y rendimientos del Tesoro de EE. UU. Es gratis y no necesitas servidor propio.

## Contenido

| Archivo | Para qué sirve |
|---|---|
| `actualizar_mercado.py` | Descarga datos, calcula indicadores y genera el tablero |
| `plantilla.html` | Diseño del tablero (los datos se insertan al ejecutar el script) |
| `requirements.txt` | Librerías de Python necesarias |
| `actualizar.yml` | Tarea diaria de GitHub Actions |
| `docs/index.html` | Tablero generado (aquí hay una versión de demostración con datos inventados) |

## Puesta en marcha (unos 15 minutos, una sola vez)

1. Crea una cuenta gratuita en github.com y un repositorio nuevo, por ejemplo `monitor-mercado`.
2. Sube los archivos de esta carpeta a la raíz del repositorio (botón *Add file → Upload files*), incluida la carpeta `docs`.
3. Crea el archivo `.github/workflows/actualizar.yml` con el contenido de `actualizar.yml` (en GitHub: *Add file → Create new file* y escribe esa ruta completa como nombre).
4. En *Settings → Pages*, elige *Deploy from a branch*, rama `main`, carpeta `/docs`. GitHub te dará una dirección web para tu tablero.
5. En la pestaña *Actions*, abre "Actualizar tablero de mercado" y pulsa *Run workflow* para la primera ejecución real. Tarda entre 8 y 15 minutos por la lista completa del S&P 500.
6. Desde entonces se actualiza solo de lunes a viernes a las 18:00 (hora de Ecuador).

Un repositorio público es lo más simple para usar Pages gratis. No guarda datos personales, solo precios de mercado.

## Uso en tu computador (opcional)

```
pip install -r requirements.txt
python actualizar_mercado.py            # datos reales, abre docs/index.html
python actualizar_mercado.py --demo     # datos inventados para probar el diseño
python actualizar_mercado.py --limite 50
```

## Personalizar

- **Qué instrumentos se siguen:** edita los diccionarios `ETFS`, `BONOS_ETF` y `FUTUROS` al inicio del script. Las acciones salen automáticamente de la lista del S&P 500 en Wikipedia.
- **Umbral de precio:** parámetro `--limite` (por defecto US$ 100). También se cambia en vivo desde el tablero.
- **Reglas del semáforo:** función `puntuar()`. Cada regla suma puntos y deja una explicación en español, que es la que ves al abrir una fila.

## Cómo se calcula el puntaje (0 a 100)

| Señal | Puntos máx. |
|---|---|
| Precio sobre su promedio de 200 días | 25 |
| Precio sobre su promedio de 50 días | 10 |
| Promedio de 50 días sobre el de 200 | 10 |
| Volatilidad baja (menos de 20 % anual) | 20 |
| RSI equilibrado (40 a 65) | 15 |
| Cerca del máximo de 52 semanas | 10 |
| Ganancia en el último año | 10 |

Verde: 70 o más. Amarillo: 45 a 69. Rojo: menos de 45. Los futuros no reciben puntaje.

## Límites que conviene conocer

- Los datos vienen de Yahoo Finance mediante `yfinance`, una vía no oficial pensada para uso personal. Puede fallar o cambiar sin aviso, y puede tener errores o retrasos. Si falla, el script no sobrescribe el tablero con datos incompletos.
- El puntaje usa solo precios pasados. No considera noticias, balances ni precio justo.
- Si Wikipedia no responde, el script usa una lista reducida de respaldo y lo avisa en el registro.
- El tablero informa; no recomienda comprar ni vender.
