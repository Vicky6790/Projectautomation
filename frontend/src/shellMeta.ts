import { createContext } from "react";

export const ShellMetaContext = createContext<(value: string) => void>(() => undefined);
