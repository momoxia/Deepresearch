/** 东八区展示，与后端 `Asia/Shanghai` / CST 语义一致 */

export const APP_TIME_ZONE = "Asia/Shanghai";

const timeHm: Intl.DateTimeFormatOptions = {
  timeZone: APP_TIME_ZONE,
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
};

const dateYmd: Intl.DateTimeFormatOptions = {
  timeZone: APP_TIME_ZONE,
  year: "numeric",
  month: "numeric",
  day: "numeric",
};

export function formatZhWallClock(isoOrDate: string | Date): string {
  return new Date(isoOrDate).toLocaleTimeString("zh-CN", timeHm);
}

export function formatZhDate(isoOrDate: string | Date): string {
  return new Date(isoOrDate).toLocaleDateString("zh-CN", dateYmd);
}
