"""Diverse, deduplicated sentence corpus for fine-tuning a natural Jessica voice.

Mix of: conversational/assistant lines, questions, phonetically-balanced sentences,
numbers/dates/units, expressive-but-natural lines, and longer sentences (for
long-form prosody / timing). All kept <= ~200 chars so clips stay <~13 s.
"""

ASSISTANT = [
    "Hello, I'm Jessica, your desktop assistant. What can I help you with today?",
    "Good morning. I hope you slept well. Shall we pick up where we left off?",
    "Of course, I can take care of that for you right now.",
    "Give me just a moment while I pull that up.",
    "All done. Let me know if you'd like me to change anything.",
    "I've saved your work and backed everything up, so you're all set.",
    "That's a great question. Let me look into it and get back to you.",
    "No problem at all. I'll handle the rest from here.",
    "I've gone ahead and scheduled that for tomorrow morning at nine.",
    "Here's a quick summary of what I found while you were away.",
    "I'm not entirely sure about that one, so let me double-check before I answer.",
    "Sorry about that. Let me try a different approach and see if it works better.",
    "Everything looks stable on my end. You're good to go.",
    "I've updated your settings, and the changes will take effect right away.",
    "Would you like me to send that now, or wait until later this afternoon?",
    "I'll keep an eye on it and let you know the moment anything changes.",
    "Let me walk you through it step by step so nothing gets missed.",
    "That should do it. The problem you described is fixed now.",
    "I added it to your list and set a reminder for Friday.",
    "Happy to help. Is there anything else you'd like me to look at?",
    "I noticed a small issue earlier, but I've already taken care of it.",
    "Your files are organized and ready whenever you need them.",
    "I'll be right here if you need anything else.",
    "Let me think about that for a second before I give you an answer.",
    "Based on what I'm seeing, the simplest fix is to restart and clear the cache.",
    "I've drafted a reply for you. Feel free to edit it however you like.",
    "It's almost finished. Just a few more seconds and it'll be ready.",
    "I went through the report and pulled out the parts that matter most.",
    "Take your time. I'll wait for you to decide how you'd like to proceed.",
    "Got it. I'll remember that for next time so you won't have to ask again.",
    "I can read your screen, run code, manage your calendar, and answer questions.",
    "Let's start with the easy stuff and work our way up from there.",
    "I'm on it. This shouldn't take long at all.",
    "Just so you know, the meeting was moved to three o'clock.",
    "I've checked everything twice, and it all looks correct.",
    "If you'd like, I can explain that in a little more detail.",
    "Done and done. What would you like to tackle next?",
    "I'll quietly run this in the background while you keep working.",
    "That makes sense. Let me adjust the plan to match what you need.",
    "Welcome back. You have two new messages and one reminder waiting.",
]

QUESTIONS = [
    "Would you like me to summarize the main points for you?",
    "Should I save this as a draft, or send it right away?",
    "Do you want the short version, or the full breakdown?",
    "Is now a good time, or would you rather I check back later?",
    "Which one would you prefer, the first option or the second?",
    "Are you ready for me to start, or do you need another minute?",
    "Did you want me to include the attachments as well?",
    "How would you like me to organize these files?",
    "Can you tell me a little more about what you're trying to do?",
    "What time works best for you tomorrow?",
    "Would it help if I broke this down into smaller steps?",
    "Have you tried turning it off and on again?",
    "Should I keep going, or stop here for now?",
    "Do you want me to remember this for next time?",
    "Where would you like me to put the finished file?",
    "Is there anything specific you're worried about?",
    "Could you double-check the spelling of that name for me?",
    "Would you like a reminder before the call starts?",
    "Are these the numbers you wanted me to use?",
    "What should I name this when I save it?",
]

PHONETIC = [
    "The birch canoe slid on the smooth planks.",
    "Glue the sheet to the dark blue background.",
    "It's easy to tell the depth of a well.",
    "These days a chicken leg is a rare dish.",
    "Rice is often served in round bowls.",
    "The juice of lemons makes fine punch.",
    "The box was thrown beside the parked truck.",
    "The hogs were fed chopped corn and garbage.",
    "Four hours of steady work faced us.",
    "A large size in stockings is hard to sell.",
    "The boy was there when the sun rose.",
    "A rod is used to catch pink salmon.",
    "The source of the huge river is the clear spring.",
    "Kick the ball straight and follow through.",
    "Help the woman get back to her feet.",
    "A pot of tea helps to pass the evening.",
    "Smoky fires lack flame and heat.",
    "The soft cushion broke the man's fall.",
    "The salt breeze came across from the sea.",
    "The girl at the booth sold fifty bonds.",
    "The small pup gnawed a hole in the sock.",
    "The fish twisted and turned on the bent hook.",
    "Press the pants and sew a button on the vest.",
    "The swan dive was far short of perfect.",
    "The beauty of the view stunned the young boy.",
    "Two blue fish swam in the tank.",
    "Her purse was full of useless trash.",
    "The colt reared and threw the tall rider.",
    "It snowed, rained, and hailed the same morning.",
    "Read verse out loud for pleasure.",
    "Hoist the load to your left shoulder.",
    "Take the winding path to reach the lake.",
    "Note closely the size of the gas tank.",
    "Wipe the grease off his dirty face.",
    "Mend the coat before you go out.",
    "The wide road shimmered in the hot sun.",
    "The lazy cow lay in the cool grass.",
    "Lift the square stone over the fence.",
    "The rope will bind the seven books at once.",
    "The sky that morning was clear and bright blue.",
    "Pack the records in a neat thin case.",
    "The crooked maze failed to fool the mouse.",
    "Faded blue jeans dried on the line.",
    "The bright lanterns lit the long hallway.",
    "Slide the tray across the glass top.",
    "The dusty bench stood under the old oak.",
    "Cats and dogs each hate the other.",
    "The pup jumped down to the deep end.",
    "The bark of the pine tree was shiny and dark.",
    "Leaves turn brown and yellow in the fall.",
]

NUMBERS_TECH = [
    "The meeting is on March third at a quarter past ten.",
    "Your order number is four eight two seven, and it ships on Friday.",
    "We saw a twelve percent jump in accuracy after the update.",
    "The file is about two hundred and fifty megabytes, so it may take a minute.",
    "Set the thermostat to sixty-eight degrees before you leave.",
    "There are twenty-four hours in a day and sixty minutes in an hour.",
    "The total comes to forty-nine dollars and ninety-nine cents.",
    "Flight 1450 departs from gate B7 at six fifteen this evening.",
    "The model has roughly five hundred million parameters.",
    "Add three cups of flour, two eggs, and half a teaspoon of salt.",
    "The download finished at ninety-eight percent and then stalled.",
    "Call me back at five five five, zero one nine three.",
    "The report covers the years 2019 through 2024.",
    "Battery is at thirty-seven percent, so you might want to plug in.",
    "The package weighs about four and a half pounds.",
    "Turn left in five hundred feet, then merge onto the highway.",
    "We need at least sixteen gigabytes of memory to run this smoothly.",
    "The discount is fifteen percent off, valid until the thirty-first.",
    "It's currently seventy-two degrees with a light breeze from the west.",
    "Version 2.5 fixed the bug that caused the app to crash on startup.",
    "The train leaves platform nine at exactly eight forty-five.",
    "Round the result to two decimal places before you save it.",
    "Our quarterly revenue grew from one point two to one point eight million.",
    "Press and hold the power button for ten seconds to reset it.",
    "The recipe serves six and takes about forty minutes from start to finish.",
]

EXPRESSIVE = [
    "Oh, that's wonderful news. I'm really happy for you.",
    "Honestly, I think this might be your best idea yet.",
    "Don't worry, this is a common issue and it's easy to fix.",
    "I know it's frustrating, but we're almost there. Hang in there.",
    "Wow, that turned out even better than I expected.",
    "Take a deep breath. We'll get through this one step at a time.",
    "I'm genuinely excited to see how this project turns out.",
    "That's completely understandable. Let's slow down and figure it out together.",
    "Nice work. You should be proud of how far you've come.",
    "Hmm, that's strange. Let me take a closer look at what's going on.",
    "Absolutely, I'd be glad to help with that.",
    "You're doing great. Just a little more and we'll be finished.",
    "Yikes, that wasn't supposed to happen. Give me a second to sort it out.",
    "I love that. Let's make it happen.",
    "It's okay to take a break. The work will still be here when you get back.",
    "Trust me, you're going to want to see this.",
    "That's a relief. I was a little worried for a moment there.",
    "Fantastic. Everything came together exactly the way we planned.",
    "I appreciate your patience while I worked through that.",
    "Let's celebrate the small wins, because they add up.",
]

LONG = [
    "When the meeting wrapped up earlier than expected, we decided to grab a coffee and talk through the rest of the plan before heading back to the office.",
    "I went ahead and backed up your files, cleared out the old logs, and restarted the service, so everything should be running smoothly again now.",
    "If you ever feel like the system is getting slow, just let me know, and I'll check what's running in the background and free up some memory for you.",
    "The afternoon light came softly through the window as the rain finally eased, and for a little while the whole room felt calm and quiet.",
    "There's something genuinely satisfying about watching a messy pile of notes slowly turn into a clear, organized plan that actually makes sense.",
    "I've been keeping track of your progress all week, and honestly, the improvement from where you started is really impressive to see.",
    "Before we get started, let me make sure I understand exactly what you need, because getting the details right now will save us time later.",
    "The old library was quiet and smelled of aged paper, and rows of tall wooden shelves stretched back farther than the eye could comfortably follow.",
    "Once the update finishes installing, the app will restart on its own, and all of your settings and preferences will be exactly where you left them.",
    "We walked along the shoreline as the tide came in, watching the waves fold over one another and slowly erase the footprints we had left behind.",
    "I know today has been a long one, so why don't we finish this last task together, and then you can call it a day with a clear conscience.",
    "The directions seemed simple enough at first, but somewhere between the third and fourth step everything got confusing, so let's go back and try again.",
    "After months of careful planning and more than a few late nights, the team finally launched the project, and the early results look very promising.",
    "If you're not happy with how it sounds, we can adjust the pacing and the tone until it feels natural, and we'll keep tweaking until it's right.",
    "Sometimes the best thing you can do is step away from the screen for a few minutes, stretch your legs, and come back with a fresh pair of eyes.",
    "The city lights flickered to life one by one as the sun dipped below the rooftops, and the streets slowly filled with the sounds of the evening.",
    "I pulled together everything from the last three meetings, removed the parts that no longer apply, and organized the rest into a single clean document.",
    "Whenever you're ready, we can go through the results together, and I'll explain what each number means and why it matters for the decision ahead.",
    "It took a lot of trial and error to get the settings just right, but now that everything is dialed in, the whole process runs without a hitch.",
    "The mountain trail wound steadily upward through the pines, and with every turn the view opened a little wider until the valley spread out below us.",
    "I understand this has been a stressful week, so let's focus on just the things that truly need to happen today and leave the rest for tomorrow.",
    "The kitchen filled with the warm smell of bread as it baked, and the steady ticking of the old clock was the only other sound in the house.",
    "We can either fix this the quick way, which will hold for now, or take a little longer and solve it properly so it never comes back again.",
    "She opened the letter slowly, unsure of what it might say, and as her eyes moved across the page a quiet smile spread over her tired face.",
    "Let me lay out the options clearly, weigh the trade-offs for each one, and then you can choose whichever path feels like the best fit for you.",
]


ASSISTANT2 = [
    "I can do that. Just point me at the folder and I'll handle the rest.",
    "Let me cross-check the numbers one more time before we call it final.",
    "Okay, I've split the document into three sections so it's easier to read.",
    "I rebooted the connection, and it looks like everything reconnected cleanly.",
    "I'll hold off on sending it until you've had a chance to review the draft.",
    "Here's what I'd recommend, but the final call is completely yours.",
    "I tucked the older versions into an archive folder so they're out of the way.",
    "Let me translate that into plain language so it's a little easier to follow.",
    "I've flagged the three items that need your attention before the deadline.",
    "Want me to set this as your default, or just use it for this one time?",
    "I'll quietly check for updates every morning and only bother you if something matters.",
    "That link looks broken, so I went and found a working one for you.",
    "I've muted the notifications for the next hour so you can focus.",
    "Let me know the magic word and I'll get started immediately.",
    "I compared the two reports and highlighted everything that changed.",
    "Your calendar is clear after lunch, so that's the best window for deep work.",
    "I'll convert it to the format you need and drop it on your desktop.",
    "There were a few duplicates in the list, so I merged them for you.",
    "I can keep this short, or go into the details. Your call.",
    "Everything's synced across your devices now, so pick up wherever you like.",
]

QUESTIONS2 = [
    "Want me to read that back to you before I send it?",
    "Should we go with the safe option, or take the bolder one?",
    "Do these results look about right to you, or did you expect something different?",
    "Would you like me to set this up as a weekly routine?",
    "Is there a deadline I should be planning around?",
    "Do you want me to keep the original, just in case?",
    "Shall I group these by date, or by name?",
    "Would a quick example help make this clearer?",
    "Are we still aiming to finish this before the weekend?",
    "Want the good news first, or the bad news?",
]

PHONETIC2 = [
    "The frosty air passed through the coat.",
    "The crooked path led straight to the barn.",
    "A cramp is no small danger on a swim.",
    "He said the same phrase thirty times.",
    "The friendly gang left the drug store.",
    "Mesh wire keeps chicks inside the pen.",
    "The frosty winds went through the fence.",
    "The young kid jumped the rusty gate.",
    "Plead with the lawyer to drop the lost cause.",
    "The wrist was badly strained and hung limp.",
    "The stray cat gave birth to kittens.",
    "The young girl gave no clear response.",
    "The meal was cooked before the bell rang.",
    "What joy there is in living each new day.",
    "A king ruled the state in the early days.",
    "The ship was torn apart on the sharp reef.",
    "Sickness kept him home the third week.",
    "The wide grin gave way to a soft laugh.",
    "Dimes showered down from all sides.",
    "They sang the same tunes at each party.",
]

NUMBERS2 = [
    "The warranty lasts for thirty-six months from the date of purchase.",
    "Mix one part bleach with ten parts water for a safe cleaning solution.",
    "The elevator stops on floors two, five, eight, and the rooftop.",
    "Our appointment is at half past four on the nineteenth of June.",
    "The average download speed was around ninety-four megabits per second.",
    "Combine the two halves and you get a whole, which seems obvious enough.",
    "Room 312 is down the hall, third door on your right.",
    "The temperature dropped from fifty-five to thirty-one overnight.",
    "We sold roughly twelve hundred units in the first three weeks.",
    "The password must be at least eight characters long with one number.",
]

NARRATIVE = [
    "She had always told herself she would travel one day, and now, with a single ticket in her hand, that day had finally come.",
    "The dog waited by the door every afternoon, ears perked at the smallest sound, certain that this would be the moment they returned.",
    "Nobody quite remembered who had started the tradition, but every year, without fail, the whole street gathered under the same old tree.",
    "He read the last line twice, closed the book gently, and sat for a long while in the quiet, letting the story settle in his chest.",
    "The first snow of the season fell overnight, and by morning the noisy world had been hushed beneath a soft and even blanket of white.",
    "They argued the whole way there, fell silent at the door, and somehow walked out an hour later as if nothing had ever come between them.",
    "Years from now, she thought, she would look back on this small ordinary evening and realize it had quietly changed everything.",
    "The market opened at dawn, and within an hour the narrow lanes were alive with color, noise, and the warm smell of fresh bread.",
    "He kept the letter in his coat pocket for weeks, reading it on the train, unsure whether it brought him more comfort or more worry.",
    "When the power finally came back on, the whole house cheered, as if surviving one quiet evening by candlelight had been a grand adventure.",
    "The garden took three full seasons to come to life, but the morning she saw the first bloom, every hour of waiting felt worth it.",
    "There was a knock at the door just past midnight, soft and uncertain, the kind that makes you wonder whether you imagined it entirely.",
]

DESCRIPTIVE = [
    "The coffee was strong and bitter, exactly the way she liked it on a cold and overcast morning.",
    "Sunlight scattered across the water, breaking into a thousand bright pieces that danced with every passing ripple.",
    "The room was warm and cluttered, full of books stacked in uneven towers and the faint smell of old paper and ink.",
    "A thin layer of dust covered the piano, untouched for years, yet it still held the quiet promise of music.",
    "The storm rolled in slowly, the sky darkening from pale gray to a deep and restless shade of blue.",
    "Worn leather boots, a faded map, and a battered compass were all he carried into the unknown.",
    "The bakery on the corner glowed with warm light, its window crowded with golden loaves and trays of glazed pastries.",
    "Outside, the wind tugged at the bare branches, and somewhere in the distance a single church bell began to ring.",
    "Her handwriting was small and careful, each letter shaped with the patience of someone who had all the time in the world.",
    "The old bridge creaked under every footstep, its iron railings cold and rough beneath the palm of his hand.",
]

EXPRESSIVE2 = [
    "Oh, come on, that's actually hilarious. I did not see that coming.",
    "Honestly? I'm a little nervous, but I think we should go for it.",
    "Phew, that was close. Good thing we caught it when we did.",
    "You know what, you're absolutely right. Let's do it your way.",
    "Aw, that's so thoughtful of you. Thank you, really.",
    "Okay, deep breath. We've got this, one step at a time.",
    "Ugh, technology. Let's just try it one more time, shall we?",
    "Yes! That worked perfectly. I'm so glad we stuck with it.",
    "Hmm, I'm not totally convinced, but I'm willing to give it a shot.",
    "That's the spirit. Now we're finally getting somewhere.",
]


def build():
    seen, out = set(), []
    for group in (ASSISTANT, QUESTIONS, PHONETIC, NUMBERS_TECH, EXPRESSIVE, LONG,
                  ASSISTANT2, QUESTIONS2, PHONETIC2, NUMBERS2, NARRATIVE, DESCRIPTIVE, EXPRESSIVE2):
        for s in group:
            s = s.strip()
            if s and s not in seen and len(s) <= 210:
                seen.add(s)
                out.append(s)
    return out


CORPUS = build()

if __name__ == "__main__":
    n = len(CORPUS)
    chars = sum(len(s) for s in CORPUS)
    lens = sorted(len(s) for s in CORPUS)
    print(f"sentences: {n}")
    print(f"total chars: {chars}  (~{chars} credits at 1/char)")
    print(f"len min/median/max: {lens[0]} / {lens[n//2]} / {lens[-1]}")
    print(f"est. audio: ~{chars/15/60:.1f} min at 15 chars/sec")
