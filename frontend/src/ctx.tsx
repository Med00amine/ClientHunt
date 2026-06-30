import { createContext, useContext } from "react";

export type DrawerKind = "opp" | "prospect";

/** What every page may ask of the shell: open a record over the page you are on, jump to another tab, or say that something changed. */
type App = {
  open: (kind: DrawerKind, id: number) => void;
  go: (tab: string, sub?: string) => void;
  rev: number;            // goes up whenever a drawer changed something, so lists behind it reload
  bump: () => void;
};

export const AppCtx = createContext<App>({ open: () => {}, go: () => {}, rev: 0, bump: () => {} });
export const useApp = () => useContext(AppCtx);
