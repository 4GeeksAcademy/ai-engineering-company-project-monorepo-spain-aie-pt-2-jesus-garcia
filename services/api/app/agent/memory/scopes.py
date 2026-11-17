"""Normalización de alcances de memoria.

El LLM propone un alcance en lenguaje natural; aquí se convierte en una clave
canónica y acotada (``carrier:SEUR:ES:rural``, ``ops:los_angeles:US:*``,
``client:cosmeticos``). No se acepta un alcance global.
"""

from __future__ import annotations

import re
import unicodedata

from .schemas import MemoryScope

CARRIER_ALIASES: dict[str, str] = {
    "ups": "UPS",
    "fedex": "FEDEX",
    "federal express": "FEDEX",
    "dhl": "DHL",
    "mrw": "MRW",
    "seur": "SEUR",
    "local": "LOCAL",
    "carrier local": "LOCAL",
    "transportista local": "LOCAL",
    "correos express": "CORREOS_EXPRESS",
}

COUNTRY_ALIASES: dict[str, str] = {
    "us": "US",
    "usa": "US",
    "eeuu": "US",
    "ee.uu.": "US",
    "estados unidos": "US",
    "spain": "ES",
    "es": "ES",
    "espana": "ES",
    "españa": "ES",
}

SITE_ALIASES: dict[str, str] = {
    "los angeles": "los_angeles",
    "los ángeles": "los_angeles",
    "los_angeles": "los_angeles",
    "losangeles": "los_angeles",
    "la": "los_angeles",
    "zaragoza": "zaragoza",
    "zgz": "zaragoza",
}

SITE_COUNTRY: dict[str, str] = {
    "los_angeles": "US",
    "zaragoza": "ES",
}

COUNTRY_LOCATION_TOKENS = {
    "us",
    "usa",
    "eeuu",
    "estados",
    "unidos",
    "los",
    "angeles",
    "es",
    "espana",
    "spain",
    "zaragoza",
}

GENERIC_CLIENT_TOKENS = {
    "cliente",
    "clientes",
    "de",
    "del",
    "la",
    "el",
    "los",
    "las",
    "un",
    "una",
    "b2b",
    "empresa",
    "marca",
}

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def normalize_text(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text or "")
    without_accents = "".join(
        char for char in decomposed if not unicodedata.combining(char)
    )
    return without_accents.lower().strip()


def slugify(value: str) -> str:
    normalized = normalize_text(value)
    slug = _SLUG_RE.sub("-", normalized).strip("-")
    return re.sub(r"-{2,}", "-", slug)


def normalize_carrier(value: str | None) -> str | None:
    if not value:
        return None
    normalized = normalize_text(value)
    if normalized in CARRIER_ALIASES:
        return CARRIER_ALIASES[normalized]
    for alias, carrier in CARRIER_ALIASES.items():
        if re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", normalized):
            return carrier
    return None


def normalize_country(value: str | None) -> str | None:
    if not value:
        return None
    normalized = normalize_text(value)
    if normalized in COUNTRY_ALIASES:
        return COUNTRY_ALIASES[normalized]
    for alias, country in COUNTRY_ALIASES.items():
        if re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", normalized):
            return country
    return None


def normalize_site(value: str | None) -> str | None:
    if not value:
        return None
    normalized = normalize_text(value).replace("_", " ").strip()
    if normalized in SITE_ALIASES:
        return SITE_ALIASES[normalized]
    for alias, site in SITE_ALIASES.items():
        if re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", normalized):
            return site
    return None


def _clean_zone(value: str | None) -> str | None:
    if not value:
        return None
    zone_stopwords = GENERIC_CLIENT_TOKENS | {"zona", "area", "área", "region", "región"}
    tokens = [
        token
        for token in normalize_text(value).replace(",", " ").split()
        if token not in zone_stopwords
        and token not in COUNTRY_LOCATION_TOKENS
    ]
    zone = slugify(" ".join(tokens))
    return zone or None


def _clean_corridor(value: str | None) -> str | None:
    if not value:
        return None
    corridor = slugify(value)
    return corridor or None


def _clean_client(value: str | None) -> str | None:
    if not value:
        return None
    tokens = [
        token
        for token in normalize_text(value).replace(",", " ").split()
        if token not in GENERIC_CLIENT_TOKENS
    ]
    client = slugify(" ".join(tokens))
    if not client or client in {"cliente", "b2b", "desconocido", "unknown"}:
        return None
    return client


def _raw(scope: dict, *keys: str) -> str | None:
    for key in keys:
        value = scope.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def normalize_scope(
    raw: dict | None,
    memory_type: str,
) -> MemoryScope | None:
    """Convierte un alcance propuesto en uno canónico o devuelve ``None``."""

    if not isinstance(raw, dict):
        return None

    declared_kind = _raw(raw, "kind", "tipo", "scope_type")
    kind_map = {
        "carrier": "carrier",
        "carrier_rule": "carrier",
        "ops": "ops",
        "operational": "ops",
        "operational_context": "ops",
        "client": "client",
        "client_preference": "client",
    }
    kind = kind_map.get((declared_kind or "").lower())
    expected = {
        "carrier_rule": "carrier",
        "operational_context": "ops",
        "client_preference": "client",
    }.get(memory_type)
    if kind is None:
        kind = expected
    if kind is None or kind != expected:
        return None

    if kind == "carrier":
        carrier = normalize_carrier(_raw(raw, "carrier", "transportista"))
        country = normalize_country(_raw(raw, "country", "pais", "país"))
        zone = _clean_zone(_raw(raw, "zone", "zona"))
        site = normalize_site(_raw(raw, "site", "sitio", "almacen", "almacén"))
        if country is None and site is not None:
            country = SITE_COUNTRY.get(site)
        if carrier is None or country is None:
            return None
        zone_key = zone or "*"
        key = f"carrier:{carrier}:{country}:{zone_key}"
        label_parts = [carrier, country]
        if zone:
            label_parts.append(f"zona {zone.replace('-', ' ')}")
        return MemoryScope(
            kind="carrier",
            carrier=carrier,
            country=country,
            zone=zone,
            site=site,
            key=key,
            label=" · ".join(label_parts),
        )

    if kind == "ops":
        site = normalize_site(_raw(raw, "site", "sitio", "almacen", "almacén"))
        country = normalize_country(_raw(raw, "country", "pais", "país"))
        if country is None and site is not None:
            country = SITE_COUNTRY.get(site)
        corridor = _clean_corridor(
            _raw(raw, "corridor", "corredor", "route", "ruta")
        )
        if site is None and corridor is None:
            return None
        site_key = site or "*"
        country_key = country or "*"
        corridor_key = corridor or "*"
        key = f"ops:{site_key}:{country_key}:{corridor_key}"
        label_parts = [
            (site or "red").replace("_", " ").title(),
            country_key,
        ]
        if corridor:
            label_parts.append(f"corredor {corridor.replace('-', ' ')}")
        return MemoryScope(
            kind="ops",
            country=country,
            site=site,
            corridor=corridor,
            key=key,
            label=" · ".join(label_parts),
        )

    client = _clean_client(_raw(raw, "client", "cliente", "client_id"))
    if client is None:
        return None
    return MemoryScope(
        kind="client",
        client=client,
        key=f"client:{client}",
        label=f"Cliente {client.replace('-', ' ')}",
    )


def scope_from_stored(
    *,
    scope_type: str,
    scope_key: str,
    scope_label: str,
    scope_json: dict | None,
) -> MemoryScope:
    """Reconstruye el alcance de una fila para mostrarlo o revalidarlo."""

    data = dict(scope_json or {})
    data.setdefault("kind", scope_type)
    data.setdefault("key", scope_key)
    data.setdefault("label", scope_label)
    return MemoryScope.model_validate(data)


__all__ = [
    "CARRIER_ALIASES",
    "COUNTRY_ALIASES",
    "SITE_ALIASES",
    "normalize_carrier",
    "normalize_country",
    "normalize_scope",
    "normalize_site",
    "normalize_text",
    "scope_from_stored",
    "slugify",
]
