import pygame
import time

pygame.mixer.init()
print("Initialized at:", pygame.mixer.get_init())
pygame.mixer.quit()

freq = int(44100 * 0.65)
pygame.mixer.init(frequency=freq)
print("Re-initialized at:", pygame.mixer.get_init())
