export const requirePublishedValue = <T>(value: T | null | undefined): T => {
  if (value === null || value === undefined)
    throw new Error("Required published evidence is absent.");
  return value;
};
