# HSLU Ilias Scraper for a daily message that includes:

##  For now just uploading some claude generated files which should work proplery, later I'll be fetching everything together to make a best possible project. 

#### Overview:

##### User Stories

- As a student I want to receive every morning around 8:00 a message with most important information of the day. 
- As a student I want to see the daily oil, gas, gold prices including some choosen important stock and etf prices
- As a student I want to know which political news are most important (world and swiss politics)
- As a student I want to know about the latest finance news
- As a student I want to know about my day, which topics will be covered in which lecture

##### TODO

- MVP: Web (Ilias) Scraper that gives a short summary of todays lectures and topics via command line. The Scraper should only be able to give out the information from a string that the User (me) will provide. (ex: "I.BA_ITEO.F2601")
- 1. Whatsapp Integration -> The summary should be sent via Whatsapp
- 2. Calendar Integration -> The Scraper has to read first the calendar and reads then the lectures of the day and will then give the summary. To the summary the date of today should be added.
- 3. News Integration -> Most Important News should be added to the summary (basic world politics ex. "Putin attacks Ukraine", and basic swiss politics ex. "Vote result NO 59% EU - Unterwerfungsvertrag")
- 4. Finance Integration -> Current Stock/ Share prices and latest oil/gas and gold prices should be addedd to the summary. ex.(UBS: 34.56 CHF ....Crude Oil: 109.92 $/barrel .... )
- 5. General Design and Output Improvements


##### Implementation
MVP: HSLU Ilias Scraper has to have some kind to intelligence (AI) - This could be implemented with a RAG system where the RAG is given all the module descriptions (PDF) where the AI should read the "SW" Semesterwoche and from there search for the suitable File - which file is for todays lectures? - In case the folder in ilias is not properly named or named according to the topics. As an alternative confirmation to make sure the RAG has choosen the correct file there could be some kind of a upload date check, as usually but now always the latest uploaded files can be the suiting file for each day. 
I should be able to give an Imput like: "I.BA_ITEO.F2601" then the scraper goes via my login to the correct course folder in Ilias and searches for the correct files, reads them and gives me a short summary so that I know which topics today will be covered. 

