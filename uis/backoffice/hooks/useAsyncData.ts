import { useCallback, useEffect, useRef, useState } from "react";

interface AsyncDataState<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
}

function depsChanged(prev: readonly unknown[], next: readonly unknown[]): boolean {
  if (prev.length !== next.length) return true;
  return prev.some((value, index) => value !== next[index]);
}

export function useAsyncData<T>(
  loader: () => Promise<T>,
  deps: readonly unknown[],
  mapError?: (err: unknown) => string,
) {
  const loaderRef = useRef(loader);
  const mapErrorRef = useRef(mapError);
  const [state, setState] = useState<AsyncDataState<T>>({
    data: null,
    loading: true,
    error: null,
  });
  const [prevDeps, setPrevDeps] = useState(deps);
  const [requestId, setRequestId] = useState(0);

  useEffect(() => {
    loaderRef.current = loader;
    mapErrorRef.current = mapError;
  }, [loader, mapError]);

  if (depsChanged(prevDeps, deps)) {
    setPrevDeps(deps);
    setRequestId((id) => id + 1);
  }

  useEffect(() => {
    let cancelled = false;
    loaderRef
      .current()
      .then((data) => {
        if (!cancelled) setState({ data, loading: false, error: null });
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setState({
            data: null,
            loading: false,
            error: mapErrorRef.current
              ? mapErrorRef.current(err)
              : err instanceof Error
                ? err.message
                : String(err),
          });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [requestId]);

  const reload = useCallback(() => {
    setState((prev) => ({ ...prev, loading: true, error: null }));
    setRequestId((id) => id + 1);
  }, []);

  return {
    ...state,
    reload,
  };
}