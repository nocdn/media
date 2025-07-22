import React, { useState, useEffect } from "react";
// using motion/react for the animation, AnimatePresence is used for the exit animation
import { AnimatePresence, motion } from "motion/react";

export default function NowPlaying({ title }: { title: string }) {
  const [currentTitle, setCurrentTitle] = useState<string>(title);

  // update the current title in the element when the title prop changes
  useEffect(() => {
    setCurrentTitle(title);
  }, [title]);

  return (
    <motion.div
      initial={{ opacity: 0, y: -10, filter: "blur(1px)" }}
      animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
      exit={{ opacity: 0, y: -10, filter: "blur(1px)" }}
      className="text-sm text-gray-500 mt-1 font-jetbrains-mono font-medium mb-3 flex items-center"
    >
      playing:
      {/* the wait mode is used to make the exiting animation finish before the entering animation starts */}
      <AnimatePresence mode="wait">
        <motion.span
          key={currentTitle}
          initial={{ opacity: 0, filter: "blur(1px)", y: -3 }}
          animate={{ opacity: 1, filter: "blur(0px)", y: 0 }}
          exit={{ opacity: 0, filter: "blur(1px)", y: 3 }}
          transition={{ duration: 0.15, ease: "easeInOut" }}
          className="text-black dark:text-gray-200 ml-1.5"
        >
          {currentTitle}
        </motion.span>
      </AnimatePresence>
    </motion.div>
  );
}
