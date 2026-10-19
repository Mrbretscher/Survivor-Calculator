import Link from "next/link";

export default function ContestantNotFound() {
  return (
    <main className="shell shellCentered">
      <section className="unavailablePanel">
        <p className="eyebrow">Contestant profile</p>
        <h1>Contestant not found</h1>
        <p>
          This contestant is not on the current prediction board. They may have
          left the game, or the profile link may be incorrect.
        </p>
        <Link className="profileLink" href="/#current-board">
          Back to current contestants →
        </Link>
      </section>
    </main>
  );
}
