import { useApp } from "../ctx";
import { SubNav } from "../ui";
import Contacts from "./Contacts";
import Files from "./Files";
import Portfolio from "./Portfolio";
import Sources from "./Sources";

const VIEWS = [["files", "Files and runs"], ["sources", "Sources"], ["portfolio", "Portfolio"], ["contacts", "Contacts"]] as [string, string][];

/** What sits behind the work: the downloads, where listings come from, the portfolio drafts may cite, and the address book. */
export default function Data({ sub }: { sub: string }) {
  const { go } = useApp();
  const view = VIEWS.some(([k]) => k === sub) ? sub : "files";
  return (
    <>
      <h2 className="sr">Data</h2>
      <SubNav label="Data" value={view} onPick={(k) => go("data", k === "files" ? "" : k)} items={VIEWS} />
      {view === "files" && <Files />}
      {view === "sources" && <Sources />}
      {view === "portfolio" && <Portfolio />}
      {view === "contacts" && <Contacts />}
    </>
  );
}
