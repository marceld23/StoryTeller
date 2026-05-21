// Field metadata for the structured world editor. Mirrors schema.py.

export type FieldSpec = {
  key: string;
  label: string;
  type: 'text' | 'textarea' | 'tags';
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
    prop: 'places',
    suggestKind: 'place',
    label: 'Orte',
    titleKey: 'name',
    fields: [
      { key: 'name', label: 'Name', type: 'text' },
      { key: 'description', label: 'Beschreibung', type: 'textarea' },
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
      { key: 'relations', label: 'Beziehungen', type: 'text' },
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
  for (const f of spec.fields) o[f.key] = f.type === 'tags' ? [] : '';
  return o;
}
