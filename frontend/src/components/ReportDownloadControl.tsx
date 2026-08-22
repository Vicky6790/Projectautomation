type Props = {
  enabled: boolean;
  onDownload: () => void;
};

export function ReportDownloadControl({ enabled, onDownload }: Props) {
  return (
    <button type="button" onClick={onDownload} disabled={!enabled}>
      Download report
    </button>
  );
}
