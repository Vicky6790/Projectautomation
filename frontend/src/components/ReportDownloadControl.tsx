type Props = {
  enabled: boolean;
  onDownload: () => void;
  label?: string;
};

export function ReportDownloadControl({
  enabled,
  onDownload,
  label = "Download report",
}: Props) {
  return (
    <button type="button" className="btn btn-outline" onClick={onDownload} disabled={!enabled}>
      {label}
    </button>
  );
}
