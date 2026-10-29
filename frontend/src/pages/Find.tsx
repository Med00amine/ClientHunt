import { useApp } from "../ctx";
import { SubNav } from "../ui";
import Listings from "./Listings";
import LiveProjects from "./LiveProjects";
import RunPanel from "./RunPanel";

/** Everything about finding clients that are already hiring: stored listings (with a search to refill them) and live client posts from Hacker News and Reddit. */
export default function Find({ sub }: { sub: string }) {
  const { go } = useApp();
  const view = sub === "live" ? "live" : "listings";
  return (
    <>
      <h2 className="sr">Find work</h2>
      <SubNav label="Find work" value={view} onPick={(k) => go("find", k === "listings" ? "" : k)} items={[["listings", "Listings"], ["live", "Live projects"]]} />
      {view === "live" ? <LiveProjects /> : <><RunPanel /><Listings /></>}
    </>
  );
}
