export function PrintViewBar({
  onSave,
  onExit,
  saving,
}: {
  onSave: () => void;
  onExit: () => void;
  saving?: boolean;
}) {
  return (
    <div className="pa-print-view-bar dms-no-print">
      <p>Printable view. Check the report, then download. One landscape page, no row splits.</p>
      <button type="button" className="btn btn-primary" onClick={onSave} disabled={saving}>
        <span className="material-symbols-outlined" aria-hidden="true">
          download
        </span>
        Download to PDF
      </button>
      <button type="button" className="btn btn-outline pa-print-view-back" onClick={onExit} disabled={saving}>
        Back to Report
      </button>
    </div>
  );
}
