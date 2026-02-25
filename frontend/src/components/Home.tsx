import clsx from "clsx";
import { memo, useMemo } from "react";

import { ChatKitPanel } from "./ChatKitPanel";
import { FactCard } from "./FactCard";
import { ThemeToggle } from "./ThemeToggle";
import { ColorScheme } from "../hooks/useColorScheme";
import { useFacts } from "../hooks/useFacts";

interface HomeProps {
  scheme: ColorScheme;
  handleThemeChange: (scheme: ColorScheme) => void;
}

const BASE_CONTAINER =
  "min-h-screen bg-gradient-to-br transition-colors duration-300";

const LAYOUT_WRAPPER =
  "mx-auto flex min-h-screen w-full max-w-6xl flex-col-reverse gap-10 px-6 pt-4 pb-10 md:py-10 lg:flex-row";

const CHAT_CONTAINER =
  "relative w-full md:w-[45%] flex h-[90vh] items-stretch overflow-hidden rounded-3xl " +
  "bg-white/80 shadow-[0_45px_90px_-45px_rgba(15,23,42,0.6)] ring-1 ring-slate-200/60 backdrop-blur " +
  "md:h-[90vh] dark:bg-slate-900/70 dark:shadow-[0_45px_90px_-45px_rgba(15,23,42,0.85)] dark:ring-slate-800/60";

function Home({ scheme, handleThemeChange }: HomeProps) {
  const { facts, refresh, performAction } = useFacts();

  const containerClass = useMemo(
    () =>
      clsx(
        BASE_CONTAINER,
        scheme === "dark"
          ? "from-slate-900 via-slate-950 to-slate-850 text-slate-100"
          : "from-slate-100 via-white to-slate-200 text-slate-900"
      ),
    [scheme]
  );

  const hasFacts = facts.length > 0;

  return (
    <main className={containerClass}>
      <div className={LAYOUT_WRAPPER}>
        {/* Chat Section */}
        <div className={CHAT_CONTAINER}>
          <ChatKitPanel
            theme={scheme}
            onWidgetAction={performAction}
            onResponseEnd={refresh}
            onThemeRequest={handleThemeChange}
          />
        </div>

        {/* Facts Section */}
        <section className="flex-1 space-y-8 py-8">
          <header className="space-y-6">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div className="space-y-3">
                <h1 className="text-3xl font-semibold sm:text-4xl">
                  ChatKit starter app
                </h1>
                <p className="max-w-xl text-sm text-slate-600 dark:text-slate-300">
                  This demo focuses on teaching ChatKit concepts and collecting
                  short, declarative facts about the user. Swap the base
                  instructions in{" "}
                  <code className="mx-1 rounded bg-slate-200 px-1.5 py-0.5 text-xs text-slate-700 dark:bg-slate-800 dark:text-slate-200">
                    app/constants.py
                  </code>{" "}
                  to experiment with different behaviours.
                </p>
              </div>

              <ThemeToggle value={scheme} onChange={handleThemeChange} />
            </div>
          </header>

          <section aria-labelledby="facts-heading">
            <h2
              id="facts-heading"
              className="text-lg font-semibold text-slate-700 dark:text-slate-200"
            >
              Saved facts
            </h2>

            <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
              Facts appear here after you share them in the conversation.
            </p>

            <div className="mt-6 rounded-3xl border border-slate-200/60 bg-white/70 shadow-[0_35px_90px_-55px_rgba(15,23,42,0.45)] ring-1 ring-slate-200/50 backdrop-blur-sm dark:border-slate-800/70 dark:bg-slate-900/50 dark:shadow-[0_45px_95px_-60px_rgba(15,23,42,0.85)] dark:ring-slate-900/60">
              <div className="max-h-[50vh] overflow-y-auto p-6 sm:max-h-[40vh]">
                {!hasFacts ? (
                  <div className="flex flex-col items-start gap-3 text-slate-600 dark:text-slate-300">
                    <span className="text-base font-medium text-slate-700 dark:text-slate-200">
                      No facts saved yet.
                    </span>
                    <span className="text-sm text-slate-500 dark:text-slate-400">
                      Start a conversation in the chat to record your first
                      fact.
                    </span>
                  </div>
                ) : (
                  <ul className="space-y-3">
                    {facts.map((fact) => (
                      <FactCard key={fact.id} fact={fact} />
                    ))}
                  </ul>
                )}
              </div>
            </div>
          </section>
        </section>
      </div>
    </main>
  );
}

export default memo(Home);
