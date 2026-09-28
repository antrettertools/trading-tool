"use client";

import { useEffect, useRef, useState } from "react";

// State that's loaded from / saved to localStorage under a key that can
// change at runtime (e.g. drawings/journal notes keyed by ticker). Reloads
// when `key` changes instead of persisting the outgoing value under the new
// key.
export function usePersistedPerKey<T>(
  key: string,
  load: (key: string) => T,
  save: (key: string, value: T) => void
) {
  const [value, setValue] = useState<T>(() => load(key));
  const keyRef = useRef(key);
  const skipSaveRef = useRef(false);

  useEffect(() => {
    if (keyRef.current !== key) {
      keyRef.current = key;
      skipSaveRef.current = true;
      setValue(load(key));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  useEffect(() => {
    if (skipSaveRef.current) {
      skipSaveRef.current = false;
      return;
    }
    save(key, value);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, value]);

  return [value, setValue] as const;
}
