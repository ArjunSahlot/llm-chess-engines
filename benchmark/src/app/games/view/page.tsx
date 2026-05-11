import { Suspense } from "react";

import { GameViewer } from "@/components/GameViewer";
import { SiteNav } from "@/components/SiteNav";

export default function GameViewPage() {
  return (
    <>
      <SiteNav />
      <main className="game-view-page page-pad">
        <Suspense fallback={<div className="loading-panel">Loading game...</div>}>
          <GameViewer />
        </Suspense>
      </main>
    </>
  );
}
