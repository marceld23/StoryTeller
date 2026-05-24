// Field metadata for the structured world editor. Mirrors schema.py.

export type FieldSpec = {
  key: string;
  label: string;
  type: 'text' | 'textarea' | 'tags' | 'select';
  /** Options for type=select (each {value, label}). */
  options?: { value: string; label: string }[];
};

export type KindSpec = {
  /** World object array property, e.g. "places" */
  prop: string;
  /** Singular suggest kind sent to the backend, e.g. "place" */
  suggestKind: string;
  label: string;
  /** title field used as the card heading */
  titleKey: string;
  fields: FieldSpec[];
};

export const CONTENT_KINDS: KindSpec[] = [
  {
    prop: 'regions',
    suggestKind: 'region',
    label: 'Regionen',
    titleKey: 'name',
    fields: [
      { key: 'name', label: 'Name', type: 'text' },
      { key: 'description', label: 'Beschreibung', type: 'textarea' },
      { key: 'tags', label: 'Tags', type: 'tags' }
    ]
  },
  {
    prop: 'places',
    suggestKind: 'place',
    label: 'Orte',
    titleKey: 'name',
    fields: [
      { key: 'name', label: 'Name', type: 'text' },
      { key: 'description', label: 'Beschreibung', type: 'textarea' },
      { key: 'region', label: 'Region (Name einer Region)', type: 'text' },
      { key: 'contains', label: 'Enthält (Sub-Orte, komma)', type: 'tags' },
      { key: 'adjacent', label: 'Grenzt an (komma)', type: 'tags' },
      { key: 'tags', label: 'Tags', type: 'tags' }
    ]
  },
  {
    prop: 'factions',
    suggestKind: 'faction',
    label: 'Fraktionen',
    titleKey: 'name',
    fields: [
      { key: 'name', label: 'Name', type: 'text' },
      { key: 'description', label: 'Beschreibung', type: 'textarea' },
      { key: 'goals', label: 'Ziele (1 Satz)', type: 'text' },
      { key: 'allies', label: 'Verbündete (komma)', type: 'tags' },
      { key: 'enemies', label: 'Gegner (komma)', type: 'tags' },
      { key: 'relations', label: 'Beziehungs-Nuancen', type: 'text' },
      { key: 'tags', label: 'Tags', type: 'tags' }
    ]
  },
  {
    prop: 'persons',
    suggestKind: 'person',
    label: 'Personen',
    titleKey: 'name',
    fields: [
      { key: 'name', label: 'Name', type: 'text' },
      { key: 'role', label: 'Rolle', type: 'text' },
      { key: 'description', label: 'Beschreibung', type: 'textarea' },
      { key: 'relations', label: 'Beziehungen (Personen, freitext)', type: 'text' },
      { key: 'faction', label: 'Fraktion (Name oder leer)', type: 'text' },
      { key: 'faction_role', label: 'Rolle in der Fraktion', type: 'text' },
      { key: 'tags', label: 'Tags', type: 'tags' }
    ]
  },
  {
    prop: 'items',
    suggestKind: 'item',
    label: 'Gegenstände',
    titleKey: 'name',
    fields: [
      { key: 'name', label: 'Name', type: 'text' },
      { key: 'description', label: 'Beschreibung', type: 'textarea' },
      { key: 'properties', label: 'Eigenschaften', type: 'textarea' },
      { key: 'tags', label: 'Tags', type: 'tags' }
    ]
  },
  {
    prop: 'creatures',
    suggestKind: 'creature',
    label: 'Kreaturen',
    titleKey: 'name',
    fields: [
      { key: 'name', label: 'Name', type: 'text' },
      { key: 'description', label: 'Beschreibung', type: 'textarea' },
      { key: 'habitat', label: 'Lebensraum (Region/Ortstyp)', type: 'text' },
      {
        key: 'threat_level',
        label: 'Gefahrenstufe',
        type: 'select',
        options: [
          { value: 'low', label: 'low — harmlos' },
          { value: 'medium', label: 'medium — gefährlich' },
          { value: 'high', label: 'high — tödlich' }
        ]
      },
      { key: 'tags', label: 'Tags', type: 'tags' }
    ]
  },
  {
    prop: 'glossary',
    suggestKind: 'glossary',
    label: 'Glossar',
    titleKey: 'term',
    fields: [
      { key: 'term', label: 'Begriff', type: 'text' },
      { key: 'definition', label: 'Definition', type: 'textarea' }
    ]
  },
  {
    prop: 'history',
    suggestKind: 'history',
    label: 'Historie',
    titleKey: 'title',
    fields: [
      { key: 'when', label: 'Zeit/Epoche', type: 'text' },
      { key: 'title', label: 'Titel', type: 'text' },
      { key: 'description', label: 'Beschreibung', type: 'textarea' }
    ]
  },
  {
    prop: 'fragments',
    suggestKind: 'fragment',
    label: 'Fragmente',
    titleKey: 'title',
    fields: [
      { key: 'title', label: 'Titel', type: 'text' },
      { key: 'text', label: 'Text', type: 'textarea' },
      { key: 'tags', label: 'Tags', type: 'tags' }
    ]
  }
];

/** Build an empty record for a given kind's fields. */
export function emptyPiece(spec: KindSpec): Record<string, unknown> {
  const o: Record<string, unknown> = {};
  for (const f of spec.fields) {
    if (f.type === 'tags') o[f.key] = [];
    else if (f.type === 'select') o[f.key] = f.options?.[0]?.value ?? '';
    else o[f.key] = '';
  }
  return o;
}
