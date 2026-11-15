"""Notificaciones en tiempo real (Server-Sent Events).

El bus vive detrás de :mod:`app.realtime.broker`: en local/tests es un fan-out
en memoria y, con ``REALTIME_BROKER=redis``, pub/sub de Redis para que el
worker Celery (proceso distinto) y la API compartan los eventos.
"""
