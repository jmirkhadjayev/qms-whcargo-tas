import QRCode from "qrcode";
import { useEffect, useState } from "react";

/** QR code rendered locally from `value` (no external service; works offline on the LAN). */
export function QrCode({
  value,
  size = 180,
  onReady,
}: {
  value: string;
  size?: number;
  onReady?: () => void;
}) {
  const [src, setSrc] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    QRCode.toDataURL(value, { width: size, margin: 1, errorCorrectionLevel: "M" }).then((url) => {
      if (!cancelled) {
        setSrc(url);
        onReady?.();
      }
    });
    return () => {
      cancelled = true;
    };
  }, [value, size, onReady]);

  if (!src) return <div style={{ width: size, height: size }} />;
  return <img src={src} width={size} height={size} alt="QR" />;
}
