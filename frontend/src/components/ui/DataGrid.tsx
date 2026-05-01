interface Row {
  key: string;
  value: string | number | React.ReactNode;
}

interface Props {
  rows: Row[];
}

export function DataGrid({ rows }: Props) {
  return (
    <div className="divide-y divide-surface-800">
      {rows.map((row) => (
        <div key={row.key} className="data-row px-3">
          <span className="data-key">{row.key}</span>
          <span className="data-val">{row.value}</span>
        </div>
      ))}
    </div>
  );
}
