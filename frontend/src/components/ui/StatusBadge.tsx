import { clsx } from "clsx";

interface Props {
  status: string;
  size?: "sm" | "xs";
}

const STATUS_STYLES: Record<string, string> = {
  ACTIVE:            "badge-green",
  AIRBORNE:          "badge-green",
  OPERATIONAL:       "badge-green",
  READY:             "badge-green",
  UNDERWAY:          "badge-blue",
  ASSEMBLING:        "badge-blue",
  IN_TRANSIT:        "badge-blue",
  PLANNED:           "badge-blue",
  DEGRADED:          "badge-amber",
  UNDER_MAINTENANCE: "badge-amber",
  CAUTION:           "badge-amber",
  SUSPENDED:         "badge-amber",
  DESTROYED:         "badge-red",
  FAILED:            "badge-red",
  ABORTED:           "badge-red",
  OFFLINE:           "badge-gray",
  RETIRED:           "badge-gray",
  DOCKED:            "badge-gray",
  COMPLETE:          "badge-gray",
};

export function StatusBadge({ status, size = "xs" }: Props) {
  const style = STATUS_STYLES[status] ?? "badge-gray";
  return (
    <span className={clsx("badge", style, size === "xs" && "text-2xs")}>
      {status.replace(/_/g, " ")}
    </span>
  );
}
